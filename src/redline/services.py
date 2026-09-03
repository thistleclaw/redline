from __future__ import annotations

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

import httpx
from googletrans import Translator

from redline.config import Config, cache_dir
from redline.database import Database
from redline.geography import find_place, normalize_place_name, places_overlap
from redline.i18n import tr
from redline.models import EmergencyStatus, Event, SourceDocument, utcnow
from redline.sources import OfficialSourceAdapter, SourceError, make_adapters


@dataclass(frozen=True, slots=True)
class SyncReport:
    source_id: str
    fetched: int = 0
    documents_added: int = 0
    events_added: int = 0
    alerts_added: int = 0
    artifacts_added: int = 0
    skipped: bool = False
    unchanged: bool = False
    error: str | None = None


class GoogleTranslator:
    """Translate short document metadata through Google Translate without local model downloads."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    async def document(self, document: SourceDocument) -> SourceDocument:
        """Translate a title and excerpt together; retain the original on any service failure."""
        if not self.enabled:
            return document
        values = [value for value in (document.title, document.excerpt[:1500]) if value.strip()]
        if not values:
            return document
        try:
            async with Translator(raise_exception=True) as translator:
                translated = await translator.translate(values, src="en", dest="ru")
        # Google Translate is an optional enhancement: a malformed response, rate limit or
        # missing network must never discard a source document or fail the source sync.
        except Exception:  # noqa: BLE001
            return document

        results = translated if isinstance(translated, list) else [translated]
        if len(results) != len(values):
            return document
        translated_values = [
            item.text.strip() if isinstance(getattr(item, "text", None), str) else ""
            for item in results
        ]
        if not all(translated_values):
            return document

        title = translated_values.pop(0) if document.title.strip() else None
        excerpt = translated_values.pop(0) if document.excerpt.strip() else None
        return replace(
            document,
            translated_title=title if title and title != document.title else None,
            translated_excerpt=excerpt if excerpt and excerpt != document.excerpt[:1500] else None,
        )


class SyncService:
    def __init__(
        self,
        database: Database,
        config: Config,
        *,
        adapters: Iterable[OfficialSourceAdapter] | None = None,
        translator: GoogleTranslator | None = None,
        document_cache_root: Path | None = None,
    ) -> None:
        self.database = database
        self.config = config
        self._adapters = list(adapters) if adapters is not None else None
        self.translator = translator or GoogleTranslator(config.translation_enabled)
        self.document_cache_root = document_cache_root or cache_dir() / "documents"

    async def sync(
        self,
        *,
        force: bool = False,
        source_id: str | None = None,
        retry_failed: bool = False,
    ) -> list[SyncReport]:
        timeout = httpx.Timeout(connect=15, read=35, write=15, pool=20)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            adapters = self._adapters or make_adapters(client, self.config.enabled_sources)
            if source_id:
                adapters = [adapter for adapter in adapters if adapter.spec.source_id == source_id]
            if retry_failed:
                failed_sources = {
                    item.source_id for item in self.database.source_health() if item.error
                }
                adapters = [
                    adapter for adapter in adapters if adapter.spec.source_id in failed_sources
                ]
            reports = [
                await self._sync_adapter(
                    adapter,
                    force=force,
                    retry_failed=retry_failed,
                )
                for adapter in adapters
            ]
        self.database.prune(
            event_retention_days=self.config.event_retention_days,
            document_cache_days=self.config.document_cache_days,
        )
        return reports

    async def _sync_adapter(
        self,
        adapter: OfficialSourceAdapter,
        *,
        force: bool,
        retry_failed: bool = False,
    ) -> SyncReport:
        source_id = adapter.spec.source_id
        health = next(
            (item for item in self.database.source_health() if item.source_id == source_id), None
        )
        retry_previous_failure = bool(retry_failed and health and health.error)
        if (
            not force
            and not retry_previous_failure
            and health
            and health.next_due
            and health.next_due > utcnow()
        ):
            return SyncReport(source_id=source_id, skipped=True)
        was_seen = self.database.source_seen(source_id)
        etag, last_modified = (None, None) if force else self.database.source_headers(source_id)
        next_due = utcnow() + adapter.spec.min_interval
        self.database.audit(
            "sync_started", f"Checking {adapter.spec.publisher}", source_id=source_id
        )
        try:
            documents, response = await adapter.fetch(etag, last_modified)
            if response.status_code == 304:
                self.database.record_source_attempt(source_id, success=True, next_due=next_due)
                self.database.audit(
                    "sync_unchanged", "Source returned 304 Not Modified", source_id=source_id
                )
                return SyncReport(source_id=source_id, unchanged=True)
            report = await self._ingest(adapter, documents, was_seen)
            self.database.record_source_attempt(
                source_id,
                success=True,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                next_due=next_due,
            )
            self.database.audit(
                "sync_succeeded",
                f"Fetched {report.fetched} official document(s)",
                source_id=source_id,
                context={
                    "documents_added": report.documents_added,
                    "events_added": report.events_added,
                    "artifacts_added": report.artifacts_added,
                },
            )
            return report
        except (httpx.HTTPError, SourceError, TimeoutError) as error:
            safe_error = str(error)[:320]
            self.database.record_source_attempt(
                source_id,
                success=False,
                error=safe_error,
                next_due=next_due,
            )
            self.database.audit("sync_failed", safe_error, source_id=source_id)
            return SyncReport(source_id=source_id, error=safe_error)

    async def _ingest(
        self, adapter: OfficialSourceAdapter, documents: list[SourceDocument], was_seen: bool
    ) -> SyncReport:
        documents_added = events_added = alerts_added = artifacts_added = 0
        active_artifacts: set[str] = set()
        for original in documents:
            document = await self.translator.document(original)
            cache_path = self._write_document_cache(document)
            document_id, inserted = self.database.save_document(document, cache_path)
            documents_added += int(inserted)
            extract_countermeasures = getattr(adapter, "extract_countermeasures", lambda _doc: ())
            for evidence in extract_countermeasures(document):
                active_artifacts.add(self.database.countermeasure_evidence_id(evidence))
                artifacts_added += int(
                    self.database.save_countermeasure_evidence(evidence, document_id)
                )
            for event in adapter.extract_events(document):
                is_new = self.database.save_event(event, document_id)
                events_added += int(is_new)
                if is_new and self._should_alert(event, was_seen):
                    reason = self._alert_reason(event)
                    alerts_added += int(self.database.create_alert(event.event_id, reason))
        if adapter.spec.source_id == "who_blueprint":
            self.database.reconcile_countermeasure_evidence(
                adapter.spec.source_id, active_artifacts
            )
        return SyncReport(
            source_id=adapter.spec.source_id,
            fetched=len(documents),
            documents_added=documents_added,
            events_added=events_added,
            alerts_added=alerts_added,
            artifacts_added=artifacts_added,
        )

    def _write_document_cache(self, document: SourceDocument) -> str:
        self.document_cache_root.mkdir(parents=True, exist_ok=True)
        path = self.document_cache_root / f"{document.content_hash}.txt"
        path.write_text(document.original_text, encoding="utf-8")
        return str(path)

    def _watch_match(self, territory: str | None) -> bool:
        if not territory:
            return False
        current_place = find_place(territory)
        current = normalize_place_name(territory)
        for watch in self.config.watch_regions:
            watch_place = find_place(watch)
            if places_overlap(current_place, watch_place):
                return True
            if current_place is not None and watch_place is not None:
                continue
            watched = normalize_place_name(watch)
            if watched and re.search(rf"(?<!\w){re.escape(watched)}(?!\w)", current):
                return True
        return False

    def _should_alert(self, event: Event, was_seen: bool) -> bool:
        if event.emergency is EmergencyStatus.PHEIC:
            return True
        if not was_seen or not self._watch_match(event.territory):
            return False
        return (
            event.source_category
            in {
                "who_don",
                "epidemiological_alert",
                "risk_assessment",
                "event_based_surveillance",
            }
            and event.evidence.value == "confirmed"
        )

    @staticmethod
    def _alert_reason(event: Event) -> str:
        if event.emergency is EmergencyStatus.PHEIC:
            return "PHEIC declared or updated by official source"
        return "Confirmed official alert affecting a watch region"


class DocumentViewer:
    """Reads local cache first; optional PDF extraction is safe text-only processing."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def text_for_event(self, event_id: str, *, language: str = "ru") -> str:
        row = self.database.document_for_event(event_id)
        if not row:
            return tr(language, "viewer.not_found")
        cached_path = Path(row["cached_path"]) if row["cached_path"] else None
        if cached_path and cached_path.exists():
            return cached_path.read_text(encoding="utf-8", errors="replace")
        return row["original_text"] or row["excerpt"]

    async def extract_pdf(self, payload: bytes, *, language: str = "ru") -> str:
        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]
        except ImportError:
            return tr(language, "viewer.pdf_missing")
        reader = PdfReader(io.BytesIO(payload))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)[:200_000]
