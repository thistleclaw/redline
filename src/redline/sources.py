from __future__ import annotations

import asyncio
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

import httpx
from bs4 import BeautifulSoup

from redline.aliases import find_disease
from redline.geography import find_place
from redline.models import (
    CountermeasureEvidence,
    EmergencyStatus,
    Event,
    EvidenceStatus,
    LocationPrecision,
    SourceDocument,
    utcnow,
)
from redline.rd import (
    WHO_BLUEPRINT_DOCUMENTS,
    WHO_TPP_DIRECTORY,
    extract_countermeasure_evidence,
)

USER_AGENT = "REDLINE/0.1 (+https://github.com/thistleclaw/redline; local-first monitoring)"


class SourceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SourceSpec:
    source_id: str
    publisher: str
    index_url: str
    category: str
    min_interval: timedelta
    allowed_hosts: tuple[str, ...]
    path_hints: tuple[str, ...] = ()
    feed_url: str | None = None
    max_documents: int = 12
    allow_index_document: bool = False


SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        "who_don",
        "WHO",
        "https://www.who.int/emergencies/disease-outbreak-news",
        "who_don",
        timedelta(minutes=15),
        ("www.who.int",),
        ("/emergencies/disease-outbreak-news/item/",),
    ),
    SourceSpec(
        "who_sitreps",
        "WHO",
        "https://www.who.int/emergencies/situation-reports",
        "situation_report",
        timedelta(minutes=30),
        ("www.who.int",),
        ("/emergencies/situation-reports/item/",),
    ),
    SourceSpec(
        "who_hed",
        "WHO Health Emergencies Programme",
        "https://extranet.who.int/publicemergency/",
        "health_emergency_dashboard",
        timedelta(minutes=30),
        ("extranet.who.int",),
        max_documents=1,
    ),
    SourceSpec(
        "cdc_outbreaks",
        "CDC",
        "https://www.cdc.gov/outbreaks/",
        "outbreak",
        timedelta(minutes=15),
        ("www.cdc.gov",),
        (),
    ),
    SourceSpec(
        "ecdc_cdtr",
        "ECDC",
        "https://www.ecdc.europa.eu/en/publications-and-data/monitoring/weekly-threats-reports",
        "risk_assessment",
        timedelta(hours=6),
        ("www.ecdc.europa.eu",),
        ("/en/publications-data/communicable-disease-threats-report-",),
    ),
    SourceSpec(
        "paho_alerts",
        "PAHO/WHO",
        "https://www.paho.org/en/epidemiological-alerts-and-updates",
        "epidemiological_alert",
        timedelta(hours=1),
        ("www.paho.org",),
        ("/en/",),
    ),
    SourceSpec(
        "africa_cdc_ebs",
        "Africa CDC",
        "https://africacdc.org/thematic-area/surveillance-and-disease-intelligence/africa-cdc-weekly-event-based-surveillance/",
        "event_based_surveillance",
        timedelta(hours=6),
        ("africacdc.org",),
        ("/download/", "/wp-content/uploads/"),
    ),
    SourceSpec(
        "who_blueprint",
        "WHO R&D Blueprint",
        WHO_BLUEPRINT_DOCUMENTS[0],
        "rd_blueprint",
        timedelta(days=1),
        ("www.who.int",),
        ("/who-r-d-blueprint/", "/prioritizing-diseases/"),
        max_documents=len(WHO_BLUEPRINT_DOCUMENTS),
        allow_index_document=True,
    ),
)


def spec_by_id(source_id: str) -> SourceSpec:
    return next(spec for spec in SPECS if spec.source_id == source_id)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for parser in (
        lambda: parsedate_to_datetime(value),
        lambda: datetime.fromisoformat(value.replace("Z", "+00:00")),
    ):
        try:
            parsed = parser()
            return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)
        except (TypeError, ValueError, IndexError):
            continue
    for pattern in ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def compact_text(node: object, *, limit: int = 10_000) -> str:
    text = node.get_text(" ", strip=True) if hasattr(node, "get_text") else str(node)
    return re.sub(r"\s+", " ", text).strip()[:limit]


PHEIC_TERM = r"(?:public health emergency of international concern|\bpheic\b)"
PHEIC_NEGATED = re.compile(
    rf"(?:does|did|would)\s+not\s+constitute[^.]*{PHEIC_TERM}|"
    rf"(?:is|was)\s+not\s+(?:a\s+)?{PHEIC_TERM}|"
    rf"no\s+{PHEIC_TERM}",
    re.IGNORECASE,
)
PHEIC_ENDED = re.compile(
    rf"no\s+longer\s+constitutes?[^.]*{PHEIC_TERM}|"
    rf"{PHEIC_TERM}[^.]{{0,100}}(?:ended|terminated|lifted|ceased)|"
    rf"(?:ended|terminated|lifted)[^.]{{0,100}}{PHEIC_TERM}",
    re.IGNORECASE,
)
PHEIC_ACTIVE = re.compile(
    rf"(?:declared|constitutes?|remains?|continues?\s+as)[^.]{{0,120}}{PHEIC_TERM}|"
    rf"{PHEIC_TERM}[^.]{{0,100}}(?:declared|ongoing|remains?\s+in\s+effect|continues?)",
    re.IGNORECASE,
)
CONFIRMED_NEGATED = re.compile(
    r"\b(?:no|zero)\s+(?:new\s+)?(?:laboratory[- ]?)?confirmed\s+cases?\b|"
    r"\b(?:case|cases|infection|infections)\s+(?:has|have|had|was|were)\s+not\s+"
    r"(?:been\s+)?confirmed\b|\bnot\s+(?:yet\s+)?confirmed\b|"
    r"\bwithout\s+(?:any\s+)?confirmed\s+cases?\b",
    re.IGNORECASE,
)
CONFIRMED_ACTIVE = re.compile(
    r"\b(?:laboratory[- ]?)?confirmed\s+(?:case|cases|infection|infections|"
    r"transmission|outbreak)\b|"
    r"\b(?:case|cases|infection|infections|outbreak)\s+(?:has|have|was|were)\s+"
    r"(?:laboratory[- ]?)?confirmed\b|"
    r"\bconfirmed\b[^.]{0,80}\b(?:case|cases|infection|infections|transmission|outbreak)\b|"
    r"\bdeclared\s+(?:an?\s+)?outbreak\b|\boutbreak\s+(?:has\s+been|was)\s+declared\b",
    re.IGNORECASE,
)
POTENTIAL_ACTIVE = re.compile(
    r"\b(?:potential|suspected|probable|possible|unconfirmed)\s+"
    r"(?:[^.;:]{1,60}\s+)?(?:case|cases|infection|infections|outbreak|transmission)\b|"
    r"\bunknown\s+cause\b",
    re.IGNORECASE,
)
REGIONAL_ACTIVE = re.compile(
    r"\b(?:declared|constitutes?|remains?)\b[^.]{0,100}"
    r"(?:public health emergency of continental security|regional emergency)\b",
    re.IGNORECASE,
)
HISTORICAL_CONTEXT = re.compile(
    r"\b(?:previously|formerly|historically|in\s+the\s+past|at\s+the\s+time|had\s+been)\b",
    re.IGNORECASE,
)
CURRENT_CONTINUITY = re.compile(
    r"\b(?:currently|ongoing|remains?|continues?|still\s+in\s+effect)\b", re.IGNORECASE
)


def _assertion_sentences(document: SourceDocument) -> list[str]:
    """Use title and concise source metadata, not unrelated mentions deep in a document."""
    excerpt = document.excerpt.strip() or document.original_text[:1800]
    raw = f"{document.title}\n{excerpt}"
    sentences = [
        re.sub(r"\s+", " ", sentence).strip()
        for sentence in re.split(r"(?<=[.!?])\s+|[\r\n]+", raw)
        if sentence.strip()
    ]
    return list(dict.fromkeys(sentences))


def _is_historical(sentence: str, reference_year: int | None) -> bool:
    years = [int(year) for year in re.findall(r"\b20\d{2}\b", sentence)]
    old_year = bool(reference_year and years and max(years) < reference_year - 1)
    historical_wording = bool(
        HISTORICAL_CONTEXT.search(sentence) and not CURRENT_CONTINUITY.search(sentence)
    )
    return old_year or historical_wording


def _emergency_status(
    sentences: Iterable[str], reference_year: int | None = None
) -> EmergencyStatus:
    pheic_sentences = [sentence for sentence in sentences if re.search(PHEIC_TERM, sentence, re.I)]
    if any(
        PHEIC_ENDED.search(sentence) and not _is_historical(sentence, reference_year)
        for sentence in pheic_sentences
    ):
        return EmergencyStatus.PHEIC_ENDED
    if any(PHEIC_NEGATED.search(sentence) for sentence in pheic_sentences):
        return EmergencyStatus.NONE
    if any(
        PHEIC_ACTIVE.search(sentence) and not _is_historical(sentence, reference_year)
        for sentence in pheic_sentences
    ):
        return EmergencyStatus.PHEIC
    if any(REGIONAL_ACTIVE.search(sentence) for sentence in sentences):
        return EmergencyStatus.REGIONAL
    return EmergencyStatus.NONE


def _evidence_status(sentences: Iterable[str], reference_year: int | None = None) -> EvidenceStatus:
    potential = False
    for sentence in sentences:
        if POTENTIAL_ACTIVE.search(sentence):
            potential = True
        if CONFIRMED_NEGATED.search(sentence):
            continue
        if CONFIRMED_ACTIVE.search(sentence) and not _is_historical(sentence, reference_year):
            return EvidenceStatus.CONFIRMED
    return EvidenceStatus.POTENTIAL if potential else EvidenceStatus.REPORTED


class OfficialSourceAdapter:
    """Fetches only public, per-source allow-listed official pages."""

    def __init__(self, spec: SourceSpec, client: httpx.AsyncClient) -> None:
        self.spec = spec
        self.client = client

    def validate_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self.spec.allowed_hosts:
            raise SourceError(f"Blocked URL outside official allow-list: {url}")
        return url

    async def request(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        self.validate_url(url)
        response = await self.client.get(url, headers=headers or {})
        if response.status_code == 304:
            return response
        response.raise_for_status()
        return response

    async def fetch(
        self, etag: str | None = None, last_modified: str | None = None
    ) -> tuple[list[SourceDocument], httpx.Response]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.1",
        }
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        root_response = await self.request(self.spec.index_url, headers)
        if root_response.status_code == 304:
            return [], root_response
        documents = await self.documents_from_response(root_response)
        return documents, root_response

    async def documents_from_response(self, response: httpx.Response) -> list[SourceDocument]:
        content_type = response.headers.get("content-type", "")
        if self.spec.feed_url or "xml" in content_type:
            return await self._from_feed_or_page(response)
        return await self._from_html_index(response)

    async def _from_feed_or_page(self, response: httpx.Response) -> list[SourceDocument]:
        feed_response = response
        if self.spec.feed_url:
            feed_response = await self.request(self.spec.feed_url, {"User-Agent": USER_AGENT})
        if "<rss" in feed_response.text or "<feed" in feed_response.text:
            return self._parse_feed(feed_response.text)
        return await self._from_html_index(feed_response)

    def _parse_feed(self, payload: str) -> list[SourceDocument]:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as error:
            raise SourceError(f"Malformed official RSS: {error}") from error
        records: list[SourceDocument] = []
        for item in root.findall(".//item")[: self.spec.max_documents]:
            title = compact_text(item.findtext("title") or "Untitled official update")
            url = (item.findtext("link") or "").strip()
            if not url:
                continue
            try:
                self.validate_url(url)
            except SourceError:
                continue
            description = compact_text(item.findtext("description") or title)
            records.append(self._document(title, url, description, item.findtext("pubDate")))
        return records

    async def _from_html_index(self, response: httpx.Response) -> list[SourceDocument]:
        soup = BeautifulSoup(response.text, "html.parser")
        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()
        for anchor in soup.select("a[href]"):
            href = urljoin(str(response.url), anchor.get("href", ""))
            title = compact_text(anchor, limit=400)
            if not title or href in seen:
                continue
            parsed = urlparse(href)
            root = urlparse(str(response.url))
            if parsed.hostname not in self.spec.allowed_hosts or parsed.scheme != "https":
                continue
            if parsed.fragment or (parsed.path.rstrip("/") == root.path.rstrip("/")):
                continue
            if self.spec.path_hints and not any(
                hint in parsed.path for hint in self.spec.path_hints
            ):
                continue
            seen.add(href)
            candidates.append((title, href))
            if len(candidates) >= self.spec.max_documents:
                break
        if not candidates and self.spec.allow_index_document:
            title = compact_text(soup.title or self.spec.publisher, limit=240)
            body, excerpt = self._clean_page(soup)
            return [self._document(title, str(response.url), body, None, excerpt=excerpt)]
        if not candidates:
            return []
        return await self._fetch_document_pages(candidates)

    async def _fetch_document_pages(
        self, candidates: Iterable[tuple[str, str]]
    ) -> list[SourceDocument]:
        records: list[SourceDocument] = []
        for fallback_title, url in candidates:
            try:
                response = await self.request(url, {"User-Agent": USER_AGENT})
                if response.headers.get("content-type", "").startswith("application/pdf"):
                    body = "PDF document. Select it in the viewer to extract text locally."
                else:
                    soup = BeautifulSoup(response.text, "html.parser")
                    body, excerpt = self._clean_page(soup)
                page = BeautifulSoup(response.text, "html.parser")
                title = compact_text(
                    page.select_one("h1") or page.title or fallback_title, limit=300
                )
                records.append(
                    self._document(
                        title,
                        url,
                        body,
                        self._find_date(body),
                        excerpt=excerpt
                        if not response.headers.get("content-type", "").startswith(
                            "application/pdf"
                        )
                        else None,
                    )
                )
            except (httpx.HTTPError, SourceError):
                # A single inaccessible document must not mark the whole official source failed.
                continue
        return records

    @staticmethod
    def _find_date(text: str) -> str | None:
        match = re.search(
            r"\b(?:\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|\d{4}-\d{2}-\d{2})\b",
            text,
        )
        return match.group(0) if match else None

    @staticmethod
    def _clean_page(soup: BeautifulSoup) -> tuple[str, str]:
        for node in soup.select(
            "script, style, nav, footer, header, noscript, form, .breadcrumb, .pagination"
        ):
            node.decompose()
        content = soup.article or soup.main or soup
        body = compact_text(content, limit=12_000)
        description = soup.select_one('meta[property="og:description"]') or soup.select_one(
            'meta[name="description"]'
        )
        excerpt = compact_text(description.get("content", ""), limit=1800) if description else ""
        if len(excerpt) < 50:
            paragraphs = [compact_text(node, limit=1800) for node in content.select("p")]
            excerpt = next((text for text in paragraphs if len(text) >= 80), body[:1800])
        return body, excerpt

    def _document(
        self,
        title: str,
        url: str,
        body: str,
        published: str | None,
        *,
        excerpt: str | None = None,
    ) -> SourceDocument:
        text = body or title
        digest = hashlib.sha256(f"{title}\n{text}".encode()).hexdigest()
        return SourceDocument(
            source_id=self.spec.source_id,
            canonical_url=url,
            title=title,
            published_at=parse_date(published),
            fetched_at=utcnow(),
            excerpt=(excerpt or text)[:1800],
            original_text=text,
            category=self.spec.category,
            content_hash=digest,
        )

    def extract_events(self, document: SourceDocument) -> list[Event]:
        sentences = _assertion_sentences(document)
        title_disease = find_disease(document.title)
        disease_sentence = next((item for item in sentences if find_disease(item)), "")
        disease = title_disease or find_disease(disease_sentence)
        event_context = "\n".join([document.title, disease_sentence, *sentences[:4]])
        place = find_place(event_context)
        lowered = event_context.casefold()
        reference_year = document.published_at.year if document.published_at else None
        emergency = _emergency_status(sentences, reference_year)
        evidence = _evidence_status(sentences, reference_year)
        territory = place.label if place else self._region_from_text(lowered)
        situation_key = "|".join(
            [
                disease.key if disease else "unclassified",
                territory or "unlocated",
                document.category,
            ]
        )
        event_id = hashlib.sha256(
            f"{document.canonical_url}|{disease.key if disease else ''}|{territory or ''}".encode()
        ).hexdigest()[:32]
        return [
            Event(
                event_id=event_id,
                document_url=document.canonical_url,
                situation_key=situation_key,
                disease_key=disease.key if disease else None,
                disease_label=disease.label if disease else None,
                territory=territory,
                latitude=place.latitude if place else None,
                longitude=place.longitude if place else None,
                location_precision=place.precision
                if place
                else LocationPrecision.REGION
                if territory
                else LocationPrecision.UNKNOWN,
                evidence=evidence,
                emergency=emergency,
                source_category=document.category,
                summary=document.excerpt,
                occurred_at=document.published_at,
            )
        ]

    def extract_countermeasures(
        self, document: SourceDocument
    ) -> tuple[CountermeasureEvidence, ...]:
        return ()

    @staticmethod
    def _region_from_text(text: str) -> str | None:
        if "americas" in text or "america region" in text:
            return "Americas"
        if "africa" in text:
            return "Africa"
        if "europe" in text:
            return "Europe"
        if "asia" in text:
            return "Asia"
        return None


class CDCOutbreakAdapter(OfficialSourceAdapter):
    """CDC's general index delegates current investigations to its active foodborne page.

    The legacy international HTML feed can contain retired URLs, so it is not treated as a live
    event feed. The dedicated current-investigations page remains an official, visible source.
    """

    current_investigations_url = "https://www.cdc.gov/foodborne-outbreaks/outbreaks/"

    async def fetch(
        self, etag: str | None = None, last_modified: str | None = None
    ) -> tuple[list[SourceDocument], httpx.Response]:
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = await self.request(self.current_investigations_url, headers)
        if response.status_code == 304:
            return [], response
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup.select("script, style, nav, footer, header, noscript"):
            node.decompose()
        body = compact_text(soup.main or soup, limit=12_000)
        title = compact_text(soup.title or "CDC current outbreak list", limit=300)
        return [self._document(title, str(response.url), body, self._find_date(body))], response


class WHODiseaseOutbreakNewsAdapter(OfficialSourceAdapter):
    """Resolve WHO's JavaScript DON index through its official OData endpoint."""

    api_url = (
        "https://www.who.int/api/emergencies/diseaseoutbreaknews"
        "?sf_provider=dynamicProvider372&sf_culture=en"
        "&$orderby=PublicationDateAndTime%20desc"
        "&$select=Title,TitleSuffix,OverrideTitle,UseOverrideTitle,regionscountries,"
        "ItemDefaultUrl,FormattedDate,PublicationDateAndTime&$top=12"
    )

    async def fetch(
        self, etag: str | None = None, last_modified: str | None = None
    ) -> tuple[list[SourceDocument], httpx.Response]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = await self.request(self.api_url, headers)
        if response.status_code == 304:
            return [], response
        try:
            items = response.json().get("value", [])
        except (ValueError, AttributeError) as error:
            raise SourceError("Malformed WHO DON API response") from error
        candidates: list[tuple[str, str]] = []
        publication_dates: dict[str, datetime] = {}
        for item in items[: self.spec.max_documents]:
            path = str(item.get("ItemDefaultUrl") or "")
            if not re.fullmatch(r"/\d{4}-DON\d+", path):
                continue
            title = str(
                item.get("OverrideTitle")
                if item.get("UseOverrideTitle") and item.get("OverrideTitle")
                else item.get("Title")
            ).strip()
            if not title:
                continue
            url = f"https://www.who.int/emergencies/disease-outbreak-news/item{path}"
            candidates.append((title, url))
            if publication_date := parse_date(str(item.get("PublicationDateAndTime") or "")):
                publication_dates[url] = publication_date
        documents = await self._fetch_document_pages(candidates)
        return [
            replace(
                document,
                published_at=publication_dates.get(document.canonical_url, document.published_at),
            )
            for document in documents
        ], response


class ECDCCDTRAdapter(OfficialSourceAdapter):
    """Keep weekly CDTR documents as multi-threat reports, not false point outbreaks."""

    def extract_events(self, document: SourceDocument) -> list[Event]:
        event = super().extract_events(document)[0]
        return [
            replace(
                event,
                disease_key=None,
                disease_label=None,
                territory="Europe",
                latitude=None,
                longitude=None,
                location_precision=LocationPrecision.REGION,
                evidence=EvidenceStatus.REPORTED,
                emergency=EmergencyStatus.NONE,
            )
        ]


class WHORDBlueprintAdapter(OfficialSourceAdapter):
    """Fetch canonical WHO Blueprint evidence pages; never emit them as outbreaks."""

    async def fetch(
        self, etag: str | None = None, last_modified: str | None = None
    ) -> tuple[list[SourceDocument], httpx.Response]:
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        # This logical source spans several independently updated WHO pages. A root-page 304
        # cannot prove that the TPP directory or a roadmap page is unchanged, so the daily
        # Blueprint poll intentionally revalidates every canonical evidence page.
        root_response = await self.request(self.spec.index_url, headers)

        documents: list[SourceDocument] = []
        root_soup = BeautifulSoup(root_response.text, "html.parser")
        for url in WHO_BLUEPRINT_DOCUMENTS:
            try:
                response = (
                    root_response
                    if url == self.spec.index_url
                    else await self.request(url, {"User-Agent": USER_AGENT})
                )
            except (httpx.HTTPError, SourceError):
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            title = compact_text(
                soup.select_one("h1") or soup.title or self.spec.publisher, limit=300
            )
            published = self._page_date(soup, compact_text(soup, limit=3000))
            body, excerpt = self._clean_page(soup)
            documents.append(
                self._document(
                    title,
                    url,
                    body,
                    published,
                    excerpt=excerpt,
                )
            )
            if url == WHO_TPP_DIRECTORY:
                documents.extend(self._tpp_link_documents(soup, url))
        documents.extend(await self._dynamic_artifact_documents(root_soup))
        return documents, root_response

    async def _dynamic_artifact_documents(self, soup: BeautifulSoup) -> list[SourceDocument]:
        candidates: list[SourceDocument] = []
        seen = set(WHO_BLUEPRINT_DOCUMENTS)
        for anchor in soup.select("a[href]"):
            label = compact_text(anchor, limit=300)
            url = urljoin(self.spec.index_url, str(anchor.get("href") or ""))
            if not label or url in seen:
                continue
            try:
                self.validate_url(url)
            except SourceError:
                continue
            link_document = self._document(label, url, label, None, excerpt=label)
            if not extract_countermeasure_evidence(link_document):
                continue
            seen.add(url)
            try:
                response = await self.request(url, {"User-Agent": USER_AGENT})
                page = BeautifulSoup(response.text, "html.parser")
                title = compact_text(page.select_one("h1") or page.title or label, limit=300)
                published = self._page_date(page, compact_text(page, limit=3000))
                body, excerpt = self._clean_page(page)
                candidates.append(
                    self._document(
                        title,
                        url,
                        body,
                        published,
                        excerpt=excerpt,
                    )
                )
            except (httpx.HTTPError, SourceError):
                candidates.append(link_document)
            if len(candidates) >= 16:
                break
        return candidates

    @classmethod
    def _page_date(cls, soup: BeautifulSoup, body: str) -> str | None:
        visible_date = soup.select_one(
            ".dynamic-content__date, .timestamp, .date, [class*='publication-date']"
        )
        if visible_date:
            parsed = cls._find_date(compact_text(visible_date, limit=120))
            if parsed:
                return parsed
        for selector, attribute in (
            ('meta[property="article:published_time"]', "content"),
            ('meta[name="date"]', "content"),
            ('meta[itemprop="datePublished"]', "content"),
            ("time[datetime]", "datetime"),
        ):
            node = soup.select_one(selector)
            if node and node.get(attribute):
                return str(node.get(attribute))
        return cls._find_date(body)

    def _tpp_link_documents(self, soup: BeautifulSoup, directory_url: str) -> list[SourceDocument]:
        documents: list[SourceDocument] = []
        seen: set[str] = set()
        for anchor in soup.select("a[href]"):
            label = compact_text(anchor, limit=300)
            if not label or not re.search(r"\b(?:TPP|PPC)s?\b", label, re.IGNORECASE):
                continue
            url = urljoin(directory_url, str(anchor.get("href") or ""))
            try:
                self.validate_url(url)
            except SourceError:
                continue
            if url in seen:
                continue
            seen.add(url)
            document = self._document(label, url, label, self._find_date(label), excerpt=label)
            if extract_countermeasure_evidence(document):
                documents.append(document)
        return documents

    def extract_events(self, document: SourceDocument) -> list[Event]:
        return []

    def extract_countermeasures(
        self, document: SourceDocument
    ) -> tuple[CountermeasureEvidence, ...]:
        return extract_countermeasure_evidence(document)


class PAHOAlertsAdapter(OfficialSourceAdapter):
    """Read PAHO alerts through the canonical index, with its working official variant."""

    fallback_suffix = "?amp=&_redline={}"
    max_index_bytes = 5_000_000
    alert_title = re.compile(
        r"\b(?:epidemiological\s+(?:alert|update)|public health emergency of international concern)\b",
        re.IGNORECASE,
    )

    def __init__(self, spec: SourceSpec, client: httpx.AsyncClient) -> None:
        super().__init__(spec, client)
        self._urllib_required = False

    async def fetch(
        self, etag: str | None = None, last_modified: str | None = None
    ) -> tuple[list[SourceDocument], httpx.Response]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.1",
        }
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        try:
            response = await self.request(self.spec.index_url, headers)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 403:
                raise
            self._urllib_required = True
            fallback_url = self.spec.index_url + self.fallback_suffix.format(time.time_ns())
            response = await asyncio.to_thread(self._urllib_request, fallback_url, headers)
        if response.status_code == 304:
            return [], response
        soup = BeautifulSoup(response.text, "html.parser")
        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()
        for anchor in soup.select("main a[href], article a[href]"):
            title = compact_text(anchor, limit=400)
            url = urljoin(self.spec.index_url, anchor.get("href", ""))
            parsed = urlparse(url)
            if (
                not self.alert_title.search(title)
                or parsed.scheme != "https"
                or parsed.hostname not in self.spec.allowed_hosts
                or not parsed.path.startswith("/en/documents/")
                or url in seen
            ):
                continue
            seen.add(url)
            candidates.append((title, url))
            if len(candidates) >= self.spec.max_documents:
                break
        if not candidates:
            raise SourceError("PAHO alert index returned no official alert documents")
        documents = await self._fetch_document_pages(candidates)
        if not documents:
            raise SourceError("PAHO returned an alert index but no readable official documents")
        return documents, response

    async def _fetch_document_pages(
        self, candidates: Iterable[tuple[str, str]]
    ) -> list[SourceDocument]:
        semaphore = asyncio.Semaphore(3)

        async def fetch_one(fallback_title: str, canonical_url: str) -> SourceDocument | None:
            headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
            try:
                async with semaphore:
                    if self._urllib_required:
                        separator = "&" if "?" in canonical_url else "?"
                        fallback_url = f"{canonical_url}{separator}_redline={time.time_ns()}"
                        response = await asyncio.to_thread(
                            self._urllib_request, fallback_url, headers
                        )
                    else:
                        try:
                            response = await self.request(canonical_url, headers)
                        except httpx.HTTPStatusError as error:
                            if error.response.status_code != 403:
                                raise
                            self._urllib_required = True
                            separator = "&" if "?" in canonical_url else "?"
                            fallback_url = f"{canonical_url}{separator}_redline={time.time_ns()}"
                            response = await asyncio.to_thread(
                                self._urllib_request, fallback_url, headers
                            )
                soup = BeautifulSoup(response.text, "html.parser")
                body, excerpt = self._clean_page(soup)
                title = compact_text(
                    soup.select_one("h1") or soup.title or fallback_title, limit=300
                )
                return self._document(
                    title,
                    canonical_url,
                    body,
                    self._find_date(f"{title} {body}"),
                    excerpt=excerpt,
                )
            except (httpx.HTTPError, SourceError):
                return None

        records = await asyncio.gather(*(fetch_one(title, url) for title, url in candidates))
        return [record for record in records if record is not None]

    def _urllib_request(self, url: str, headers: dict[str, str]) -> httpx.Response:
        """Use a proxy-free stdlib TLS profile when Pantheon rejects httpx with HTTP 403."""
        self.validate_url(url)
        request = Request(url, headers=headers, method="GET")
        opener = build_opener(ProxyHandler({}), HTTPSHandler())
        try:
            with opener.open(request, timeout=35) as raw_response:
                status = raw_response.status
                final_url = raw_response.geturl()
                response_headers = dict(raw_response.headers.items())
                content = raw_response.read(self.max_index_bytes + 1)
        except HTTPError as error:
            status = error.code
            final_url = error.geturl()
            response_headers = dict(error.headers.items()) if error.headers else {}
            content = error.read(self.max_index_bytes + 1)
        except (OSError, URLError) as error:
            raise SourceError(f"PAHO fallback request failed: {error}") from error
        self.validate_url(final_url)
        if len(content) > self.max_index_bytes:
            raise SourceError("PAHO alert index exceeded the 5 MB response limit")
        response = httpx.Response(
            status,
            headers=response_headers,
            content=content,
            request=httpx.Request("GET", final_url, headers=headers),
        )
        if response.status_code != 304:
            response.raise_for_status()
        return response


class WHOHealthEmergencyDashboardAdapter(OfficialSourceAdapter):
    """Treat the visible WHO dashboard page as one dated official situational layer."""

    async def fetch(
        self, etag: str | None = None, last_modified: str | None = None
    ) -> tuple[list[SourceDocument], httpx.Response]:
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = await self.request(self.spec.index_url, headers)
        if response.status_code == 304:
            return [], response
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup.select("script, style, nav, footer, header, noscript"):
            node.decompose()
        title = compact_text(soup.title or "WHO Health Emergency Dashboard", limit=300)
        body = compact_text(soup.main or soup, limit=15_000)
        return [self._document(title, str(response.url), body, self._find_date(body))], response


def make_adapters(
    client: httpx.AsyncClient, enabled: Iterable[str] | None = None
) -> list[OfficialSourceAdapter]:
    enabled_set = set(enabled) if enabled is not None else {spec.source_id for spec in SPECS}
    return [
        WHODiseaseOutbreakNewsAdapter(spec, client)
        if spec.source_id == "who_don"
        else CDCOutbreakAdapter(spec, client)
        if spec.source_id == "cdc_outbreaks"
        else ECDCCDTRAdapter(spec, client)
        if spec.source_id == "ecdc_cdtr"
        else PAHOAlertsAdapter(spec, client)
        if spec.source_id == "paho_alerts"
        else WHORDBlueprintAdapter(spec, client)
        if spec.source_id == "who_blueprint"
        else WHOHealthEmergencyDashboardAdapter(spec, client)
        if spec.source_id == "who_hed"
        else OfficialSourceAdapter(spec, client)
        for spec in SPECS
        if spec.source_id in enabled_set
    ]


async def close_client_after(
    client: httpx.AsyncClient, coroutines: Iterable[object]
) -> list[object]:
    try:
        return await asyncio.gather(*coroutines)
    finally:
        await client.aclose()
