from __future__ import annotations

import json

import httpx
import pytest

from redline.ai import (
    GeminiClient,
    GeminiError,
    GeminiResult,
    generate_test_scenario,
    generate_test_timelapse,
    ingest_test_scenario,
    monitor_context,
)
from redline.config import Config
from redline.database import Database


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
