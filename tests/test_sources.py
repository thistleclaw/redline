from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from redline.sources import (
    USER_AGENT,
    CDCOutbreakAdapter,
    ECDCCDTRAdapter,
    OfficialSourceAdapter,
    PAHOAlertsAdapter,
    SourceSpec,
    WHODiseaseOutbreakNewsAdapter,
    WHOHealthEmergencyDashboardAdapter,
    WHORDBlueprintAdapter,
    make_adapters,
    spec_by_id,
)


def test_user_agent_points_to_the_real_repository():
    assert "github.com/thistleclaw/redline" in USER_AGENT
    assert "github.com/redline-epivigil" not in USER_AGENT


@pytest.mark.asyncio
async def test_html_adapter_fetches_only_official_document_links():
    spec = SourceSpec(
        "test",
        "Test Ministry",
        "https://health.example.test/index",
        "epidemiological_alert",
        timedelta(minutes=15),
        ("health.example.test",),
        ("/document/",),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/index":
            return httpx.Response(
                200,
                text='<a href="/document/ebola">Official Ebola update</a><a href="https://bad.example/x">bad</a>',
                headers={"content-type": "text/html"},
            )
        return httpx.Response(
            200,
            text="<html><title>Ebola outbreak confirmed in Rwanda</title><main>Confirmed Ebola outbreak in Rwanda. 1 September 2026.</main></html>",
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OfficialSourceAdapter(spec, client)
        documents, response = await adapter.fetch()
    assert response.status_code == 200
    assert len(documents) == 1
    events = adapter.extract_events(documents[0])
    assert events[0].disease_key == "ebola"
    assert events[0].territory == "Rwanda"


@pytest.mark.asyncio
async def test_adapter_honours_not_modified_response():
    spec = SourceSpec(
        "test",
        "Test",
        "https://health.example.test/index",
        "alert",
        timedelta(minutes=15),
        ("health.example.test",),
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(304))
    ) as client:
        documents, response = await OfficialSourceAdapter(spec, client).fetch(etag="same")
    assert response.status_code == 304
    assert documents == []


@pytest.mark.asyncio
async def test_html_feed_fragment_is_parsed_as_official_html_feed():
    spec = SourceSpec(
        "test",
        "Test",
        "https://health.example.test/index",
        "alert",
        timedelta(minutes=15),
        ("health.example.test",),
        feed_url="https://health.example.test/feed.html",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed.html":
            return httpx.Response(200, text='<a href="/doc">Official update</a>')
        if request.url.path == "/doc":
            return httpx.Response(
                200,
                text="<title>Confirmed Ebola in Rwanda</title><main>Confirmed Ebola in Rwanda.</main>",
            )
        return httpx.Response(200, text="<html>Index</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        documents, _ = await OfficialSourceAdapter(spec, client).fetch()
    assert documents[0].title == "Confirmed Ebola in Rwanda"


@pytest.mark.asyncio
async def test_cdc_adapter_uses_current_investigations_not_retired_feed():
    spec = SourceSpec(
        "cdc_outbreaks",
        "CDC",
        "https://www.cdc.gov/outbreaks/",
        "outbreak",
        timedelta(minutes=15),
        ("www.cdc.gov",),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/foodborne-outbreaks/outbreaks/"
        return httpx.Response(
            200,
            text="<title>Current Outbreaks</title><main>Active Salmonella investigation.</main>",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        documents, _ = await CDCOutbreakAdapter(spec, client).fetch()
    assert documents[0].title == "Current Outbreaks"
    assert (
        CDCOutbreakAdapter(spec, client).extract_events(documents[0])[0].disease_key == "salmonella"
    )


@pytest.mark.asyncio
async def test_dashboard_adapter_keeps_dashboard_canonical_url_not_a_fragment_link():
    spec = SourceSpec(
        "who_hed",
        "WHO",
        "https://health.example.test/dashboard",
        "dashboard",
        timedelta(minutes=30),
        ("health.example.test",),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text="<title>WHO dashboard</title><main>Dashboard PHEIC update</main><a href='#'>skip</a>",
            )
        )
    ) as client:
        documents, _ = await WHOHealthEmergencyDashboardAdapter(spec, client).fetch()
    assert documents[0].canonical_url == spec.index_url
    assert (
        WHOHealthEmergencyDashboardAdapter(spec, client)
        .extract_events(documents[0])[0]
        .emergency.value
        == "none"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("excerpt", "emergency", "evidence"),
    [
        ("WHO determined that the event does not constitute a PHEIC.", "none", "reported"),
        ("WHO determined that the event constitutes a PHEIC.", "pheic", "reported"),
        ("WHO determined that the event no longer constitutes a PHEIC.", "pheic_ended", "reported"),
        ("The event was declared a PHEIC in 2020.", "none", "reported"),
        ("The event was previously declared a PHEIC.", "none", "reported"),
        ("The PHEIC ended in 2020.", "none", "reported"),
        ("The previously declared PHEIC remains in effect.", "pheic", "reported"),
        ("No confirmed cases have been reported.", "none", "reported"),
        (
            "A suspected case remains under investigation; no confirmed cases exist.",
            "none",
            "potential",
        ),
        ("A laboratory-confirmed Ebola case was reported.", "none", "confirmed"),
    ],
)
async def test_generic_extraction_is_sentence_scoped_and_negation_aware(
    document, excerpt, emergency, evidence
):
    spec = SourceSpec(
        "test",
        "Test authority",
        "https://health.example.test/index",
        "epidemiological_alert",
        timedelta(minutes=15),
        ("health.example.test",),
    )
    candidate = replace(
        document,
        title="Ebola update - Rwanda",
        excerpt=excerpt,
        original_text=excerpt,
    )
    async with httpx.AsyncClient() as client:
        event = OfficialSourceAdapter(spec, client).extract_events(candidate)[0]

    assert event.emergency.value == emergency
    assert event.evidence.value == evidence


@pytest.mark.asyncio
async def test_generic_extraction_ignores_unrelated_deep_document_mentions(document):
    spec = SourceSpec(
        "test",
        "Test authority",
        "https://health.example.test/index",
        "epidemiological_alert",
        timedelta(minutes=15),
        ("health.example.test",),
    )
    candidate = replace(
        document,
        title="Cholera update - Rwanda",
        excerpt="A suspected cholera case is under investigation in Rwanda.",
        original_text=(
            "A suspected cholera case is under investigation in Rwanda. "
            "Historical appendix: Ebola was declared a PHEIC in 2020."
        ),
    )
    async with httpx.AsyncClient() as client:
        event = OfficialSourceAdapter(spec, client).extract_events(candidate)[0]

    assert event.disease_key == "cholera"
    assert event.emergency.value == "none"
    assert event.evidence.value == "potential"


@pytest.mark.asyncio
async def test_who_don_adapter_resolves_official_api_and_keeps_clean_ebola_summary():
    spec = SourceSpec(
        "who_don",
        "WHO",
        "https://www.who.int/emergencies/disease-outbreak-news",
        "who_don",
        timedelta(minutes=15),
        ("www.who.int",),
        ("/emergencies/disease-outbreak-news/item/",),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/emergencies/diseaseoutbreaknews":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "ItemDefaultUrl": "/2026-DON616",
                            "PublicationDateAndTime": "2026-08-28T15:28:00Z",
                            "UseOverrideTitle": True,
                            "OverrideTitle": "Ebola disease - Democratic Republic of the Congo",
                            "Title": "Ignored title",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            text="""
                <html><head>
                <meta property="og:description" content="Confirmed Ebola transmission continues in the Democratic Republic of the Congo. The outbreak remains a public health emergency of international concern.">
                </head><body><nav>Ukraine unrelated navigation</nav><article>
                <h1>Ebola disease - Democratic Republic of the Congo</h1>
                Confirmed Ebola outbreak in the Democratic Republic of the Congo.
                Public health emergency of international concern.
                </article></body></html>
            """,
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = WHODiseaseOutbreakNewsAdapter(spec, client)
        documents, _ = await adapter.fetch()

    assert len(documents) == 1
    assert documents[0].published_at.isoformat() == "2026-08-28T15:28:00+00:00"
    assert documents[0].excerpt.startswith("Confirmed Ebola transmission")
    assert "Ukraine" not in documents[0].original_text
    event = adapter.extract_events(documents[0])[0]
    assert (event.disease_key, event.territory, event.emergency.value) == (
        "ebola",
        "Democratic Republic of the Congo",
        "pheic",
    )


@pytest.mark.asyncio
async def test_ecdc_adapter_skips_navigation_and_keeps_report_off_the_outbreak_map():
    spec = SourceSpec(
        "ecdc_cdtr",
        "ECDC",
        "https://www.ecdc.europa.eu/en/publications-and-data/monitoring/weekly-threats-reports",
        "risk_assessment",
        timedelta(hours=6),
        ("www.ecdc.europa.eu",),
        ("/en/publications-data/communicable-disease-threats-report-",),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "weekly-threats-reports" in request.url.path:
            return httpx.Response(
                200,
                text="""
                    <a href="#main-content">Skip navigation</a>
                    <a href="/en/publications-and-data/planned-scientific-outputs">Junk</a>
                    <a href="/en/publications-data/communicable-disease-threats-report-week-35">Communicable disease threats report, week 35</a>
                """,
            )
        return httpx.Response(
            200,
            text="""
                <head><meta name="description" content="This issue includes verified updates on Ebola and cholera."></head>
                <article><h1>Communicable disease threats report, week 35</h1>
                Generic publication chrome. Ebola in the Democratic Republic of the Congo.
                </article>
            """,
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = ECDCCDTRAdapter(spec, client)
        documents, _ = await adapter.fetch()

    assert len(documents) == 1
    assert documents[0].excerpt == "This issue includes verified updates on Ebola and cholera."
    event = adapter.extract_events(documents[0])[0]
    assert event.disease_key is None
    assert event.latitude is None and event.longitude is None


@pytest.mark.asyncio
async def test_paho_adapter_falls_back_after_403_and_selects_only_alert_documents(monkeypatch):
    spec = SourceSpec(
        "paho_alerts",
        "PAHO/WHO",
        "https://www.paho.org/en/epidemiological-alerts-and-updates",
        "epidemiological_alert",
        timedelta(hours=1),
        ("www.paho.org",),
        ("/en/",),
        max_documents=2,
    )
    requests: list[httpx.Request] = []
    index_html = """
        <main>
          <nav><a href="/en/about">About PAHO</a></nav>
          <a href="/en/documents/epidemiological-update-avian-influenza-2026">
            Epidemiological Update Avian Influenza A(H5) - 26 August 2026
          </a>
          <a href="/en/news/unrelated">Unrelated PAHO news</a>
          <a href="/en/documents/epidemiological-alert-measles-2026">
            Epidemiological Alert Measles - 7 August 2026
          </a>
        </main>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(403, text="Forbidden")

    def fallback_request(adapter, url, headers):
        request = httpx.Request("GET", url, headers=headers)
        requests.append(request)
        if request.url.path != "/en/epidemiological-alerts-and-updates":
            title = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                text=f"""
                    <head><meta name="description" content="Official PAHO alert document with confirmed regional surveillance information."></head>
                    <main><h1>{title}</h1>
                    Confirmed avian influenza in the Americas. 26 August 2026.
                    <a href="/sites/default/files/2026/08/official-alert.pdf">PDF</a></main>
                """,
                headers={"content-type": "text/html"},
                request=request,
            )
        return httpx.Response(
            200,
            text=index_html,
            headers={"content-type": "text/html", "etag": '"fallback"'},
            request=request,
        )

    monkeypatch.setattr(PAHOAlertsAdapter, "_urllib_request", fallback_request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = PAHOAlertsAdapter(spec, client)
        documents, response = await adapter.fetch()

    assert response.status_code == 200
    assert response.headers["etag"] == '"fallback"'
    assert len(documents) == 2
    assert all(
        document.canonical_url.startswith("https://www.paho.org/en/documents/")
        for document in documents
    )
    assert all("About PAHO" not in document.title for document in documents)
    assert requests[0].url.query == b""
    assert requests[1].url.params.get("amp") == ""
    assert requests[1].url.params.get("_redline")


@pytest.mark.asyncio
async def test_paho_source_uses_the_specialized_adapter():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    ) as client:
        adapters = make_adapters(client, enabled=["paho_alerts"])
        assert len(adapters) == 1
        assert isinstance(adapters[0], PAHOAlertsAdapter)


@pytest.mark.asyncio
async def test_blueprint_adapter_fetches_canonical_pages_and_structured_tpp_links():
    spec = spec_by_id("who_blueprint")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        title = "WHO R&D Blueprint"
        body = "Official WHO Blueprint reference."
        if "links-to-who-tpps" in request.url.path:
            title = "Links to WHO TPPs and PPCs"
            body = (
                '<a href="/publications/m/item/who-target-product-profiles-for-mers-cov-vaccines">'
                "WHO MERS coronavirus vaccines TPP</a>"
            )
        return httpx.Response(
            200,
            text=(
                f'<html><div class="dynamic-content__date">3 March 2026</div>'
                f"<main><h1>{title}</h1><p>{body}</p></main></html>"
            ),
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = WHORDBlueprintAdapter(spec, client)
        documents, response = await adapter.fetch(etag='"root-only"')

    assert response.status_code == 200
    assert "if-none-match" not in requests[0].headers
    assert adapter.extract_events(documents[0]) == []
    assert documents[0].published_at.isoformat().startswith("2026-03-03")
    linked = next(
        document for document in documents if "mers-cov-vaccines" in document.canonical_url
    )
    evidence = adapter.extract_countermeasures(linked)
    assert [(item.pathogen_key, item.kind) for item in evidence] == [("mers_sars", "vaccines")]
