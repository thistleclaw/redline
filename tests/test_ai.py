from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from redline.ai import (
    GeminiClient,
    GeminiError,
    GeminiResult,
    generate_test_model,
    generate_test_scenario,
    generate_test_timelapse,
    ingest_test_scenario,
    monitor_context,
)
from redline.config import Config
from redline.database import Database
from redline.models import CountermeasureEvidence


@pytest.mark.asyncio
async def test_gemini_uses_primary_then_fallback_without_key_in_url():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "gemini-3.5-flash-lite" in request.url.path:
            return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "answer"}]}}]},
        )

    config = Config(ai_models=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"])
    client = GeminiClient(
        config,
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    )

    result = await client.generate("question", system_instruction="system")

    assert result == GeminiResult("answer", "gemini-3.1-flash-lite")
    assert [request.url.path.split("/")[-1] for request in requests] == [
        "gemini-3.5-flash-lite:generateContent",
        "gemini-3.1-flash-lite:generateContent",
    ]
    assert all(request.headers["x-goog-api-key"] == "test-secret" for request in requests)
    assert all("test-secret" not in str(request.url) for request in requests)


@pytest.mark.asyncio
async def test_gemini_requires_an_environment_explicit_or_stored_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("redline.ai.load_gemini_api_key", lambda: None)
    client = GeminiClient(Config())

    with pytest.raises(GeminiError, match="not configured"):
        await client.generate("question", system_instruction="system")


def test_gemini_uses_environment_before_persistent_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "environment-key")
    monkeypatch.setattr(
        "redline.ai.load_gemini_api_key",
        lambda: pytest.fail("persistent key must not be read when an environment key exists"),
    )

    client = GeminiClient(Config())

    assert client.api_key == "environment-key"


@pytest.mark.asyncio
async def test_gemini_uses_stable_generate_content_fields_for_structured_json():
    request_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": '{"events": []}'}]}}]},
        )

    client = GeminiClient(
        Config(ai_models=["gemini-3.5-flash-lite"]),
        api_key="test-secret",
        transport=httpx.MockTransport(handler),
    )
    schema = {"type": "object", "properties": {"events": {"type": "array"}}}

    await client.generate("scenario", system_instruction="system", response_schema=schema)

    generation_config = request_payloads[0]["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseJsonSchema"] == schema
    assert "responseFormat" not in generation_config


def test_monitor_context_contains_normalized_events_not_full_documents(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    document_id, _ = database.save_document(document)
    database.save_event(event, document_id)
    rd_document = replace(
        document,
        source_id="who_blueprint",
        canonical_url="https://www.who.int/publications/m/item/filovirus-roadmap",
        content_hash="rd-document",
    )
    rd_document_id, _ = database.save_document(rd_document)
    database.save_countermeasure_evidence(
        CountermeasureEvidence(
            pathogen_key="filoviruses",
            pathogen_family="Filoviridae",
            kind="roadmap",
            label="Filovirus R&D roadmap",
            url=rd_document.canonical_url,
            status="published",
            published_at=rd_document.published_at,
            checked_at=rd_document.fetched_at,
        ),
        rd_document_id,
    )

    payload = json.loads(
        monitor_context(
            database,
            Config(initialized=True),
            focus="world",
            filters={},
            test_mode=False,
        )
    )

    assert payload["event_count"] == 1
    assert payload["events"][0]["source_url"] == document.canonical_url
    assert payload["events"][0]["map_scope"] == "local"
    assert "original_text" not in payload["events"][0]
    assert payload["countermeasure_evidence"][0]["pathogen_family"] == "Filoviridae"


@pytest.mark.asyncio
async def test_ai_test_scenario_is_validated_and_ingested_only_into_target_database(tmp_path):
    scenario_events = [
        {
            "title": f"Synthetic anthrax signal {index}",
            "disease": "Anthrax",
            "territory": f"Eurasia sector {index}",
            "latitude": 45.0 + index,
            "longitude": 50.0 + index * 20,
            "evidence": "confirmed",
            "emergency": "regional",
            "summary": "Synthetic event for interface testing only.",
        }
        for index in range(3)
    ]

    class FakeClient:
        async def generate(self, prompt, *, system_instruction, response_schema=None):
            assert "SYNTHETIC TEST SCENARIO" in prompt
            assert response_schema is not None
            return GeminiResult(
                json.dumps(
                    {
                        "title": "Anthrax across Eurasia",
                        "events": scenario_events,
                    }
                ),
                "gemini-3.5-flash-lite",
            )

    live_database = Database(tmp_path / "live.sqlite3")
    test_database = Database(tmp_path / "test.sqlite3")
    scenario = await generate_test_scenario(FakeClient(), "anthrax", "en")
    count = ingest_test_scenario(test_database, scenario)

    assert count == 3
    assert live_database.events() == []
    row = test_database.events()[0]
    assert row["source_id"] == "redline_test_ai"
    assert row["source_category"] == "test_scenario"
    assert row["map_status"] == "outbreak"
    assert row["unread_alert"] == 1
    assert row["canonical_url"].startswith("redline-test://")


@pytest.mark.asyncio
async def test_ai_timelapse_validates_and_orders_weekly_events():
    events = [
        {
            "title": f"Synthetic event {index}",
            "disease": "Ebola",
            "territory": f"Test region {index}",
            "latitude": float(index),
            "longitude": 20.0 + index,
            "evidence": "confirmed",
            "emergency": "none",
            "summary": "Synthetic time-lapse event only.",
            "map_status": "extinction" if week == 2 else "spread",
            "map_scope": "global" if week == 2 else "region",
            "week": week,
        }
        for index, week in enumerate((2, 0, 1, 0, 2, 1))
    ]

    class FakeClient:
        async def generate(self, prompt, *, system_instruction, response_schema=None):
            assert "SYNTHETIC TEST TIMELAPSE" in prompt
            assert "never for disease decline" in system_instruction
            assert "map_scope" in response_schema["properties"]["events"]["items"]["required"]
            return GeminiResult(
                json.dumps({"title": "Synthetic spread", "duration_weeks": 2, "events": events}),
                "gemini-3.5-flash-lite",
            )

    result = await generate_test_timelapse(FakeClient(), "test spread", "en")

    assert result.duration_weeks == 2
    assert [event["week"] for event in result.events] == [0, 0, 1, 1, 2, 2]
    assert result.events[-1]["map_status"] == "extinction"
    assert result.events[-1]["map_scope"] == "global"


@pytest.mark.asyncio
async def test_ai_timelapse_honors_an_explicit_multi_year_duration():
    events = [
        {
            "title": f"Synthetic event {index}",
            "disease": "Anthrax",
            "territory": f"Test region {index}",
            "latitude": float(index),
            "longitude": 20.0 + index,
            "evidence": "confirmed",
            "emergency": "regional",
            "summary": "Synthetic time-lapse event only.",
            "week": week,
        }
        for index, week in enumerate((0, 20, 52, 78, 120, 156))
    ]

    class FakeClient:
        async def generate(self, prompt, *, system_instruction, response_schema=None):
            assert "exactly 156 weeks" in system_instruction
            assert response_schema["properties"]["duration_weeks"]["maximum"] == 520
            assert "maxItems" not in response_schema["properties"]["events"]
            return GeminiResult(
                json.dumps({"title": "Three year spread", "duration_weeks": 52, "events": events}),
                "gemini-3.5-flash-lite",
            )

    result = await generate_test_timelapse(
        FakeClient(), "three year spread", "en", requested_duration_weeks=156
    )

    assert result.duration_weeks == 156
    assert result.events[-1]["week"] == 156


@pytest.mark.asyncio
async def test_ai_model_uses_numpy_for_outcomes_then_gemini_for_explanation():
    payload = {
        "title": "Local model",
        "disease": "Test virus",
        "duration_days": 84,
        "rationale": "A bounded synthetic hypothesis",
        "parameters": {
            "r0": 2.0,
            "latent_days": 4.0,
            "infectious_days": 6.0,
            "asymptomatic_fraction": 0.2,
            "asymptomatic_relative_infectiousness": 0.5,
            "hospitalization_fraction": 0.05,
            "hospital_stay_days": 8.0,
            "infection_fatality_ratio": 0.01,
            "immunity_waning_days": 0.0,
            "vaccine_start_day": 30,
            "vaccination_per_1000_per_day": 0.0,
            "vaccine_effectiveness": 0.0,
            "vaccine_waning_days": 0.0,
            "seasonal_amplitude": 0.0,
            "seasonal_peak_day": 0,
            "mobility_rate": 0.0,
            "mobility_distance_km": 1000.0,
            "uncertainty_fraction": 0.0,
        },
        "locations": [
            {
                "name": "Test city",
                "latitude": 50.0,
                "longitude": 30.0,
                "population": 500_000,
                "initial_exposed": 20,
                "initial_infectious": 5,
                "initial_recovered_fraction": 0.0,
                "initial_vaccinated_fraction": 0.0,
                "daily_importations": 0.0,
                "travel_weight": 1.0,
            }
        ],
        "interventions": [],
    }

    class FakeClient:
        requests = []

        async def generate(self, prompt, *, system_instruction, response_schema=None):
            self.requests.append((prompt, system_instruction, response_schema))
            if response_schema is not None:
                assert "MODEL PARAMETERS" in system_instruction
                assert "never generate outcome rows" in system_instruction
                assert "events" not in response_schema["properties"]
                return GeminiResult(json.dumps(payload), "gemini-3.5-flash-lite")
            assert "SEIR_RESULT_JSON" in prompt
            assert "Do not recalculate" in system_instruction
            assert '"deterministic_summary"' in prompt
            return GeminiResult(
                "The local model reaches its active-infection peak during the scenario.",
                "gemini-3.1-flash-lite",
            )

    client = FakeClient()
    result = await generate_test_model(client, "test epidemic", "en", requested_duration_weeks=20)

    assert result.duration_weeks == 20
    assert result.engine == "numpy_seir"
    assert result.events
    assert all(event["emergency"] == "none" for event in result.events)
    assert "NumPy SEAIRHDV" in result.model
    assert "explanation: gemini-3.1-flash-lite" in result.model
    assert result.summary.startswith("The local model")
    assert len(client.requests) == 2
