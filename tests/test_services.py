from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest

from redline.config import Config
from redline.database import Database
from redline.models import utcnow
from redline.services import GoogleTranslator, SyncService
from redline.sources import SourceSpec


class FakeAdapter:
    def __init__(self, document, event) -> None:
        self.spec = SourceSpec(
            "who_don",
            "WHO",
            "https://www.who.int/index",
            "who_don",
            timedelta(minutes=15),
            ("www.who.int",),
        )
        self.document = document
        self.event = event
        self.fetch_headers = []

    async def fetch(self, etag=None, last_modified=None):
        self.fetch_headers.append((etag, last_modified))
        return [self.document], httpx.Response(200, headers={"etag": "v1"})

    def extract_events(self, document):
        return [self.event]


@pytest.mark.asyncio
async def test_google_translate_translates_short_metadata_without_a_model(monkeypatch, document):
    class FakeGoogleClient:
        def __init__(self, **kwargs):
            assert kwargs == {"raise_exception": True}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return None

        async def translate(self, values, *, src, dest):
            assert values == [document.title, document.excerpt]
            assert (src, dest) == ("en", "ru")
            return [SimpleNamespace(text="Переведённый заголовок"), SimpleNamespace(text="Перевод")]

    monkeypatch.setattr("redline.services.Translator", FakeGoogleClient)

    translated = await GoogleTranslator().document(document)

    assert translated.translated_title == "Переведённый заголовок"
    assert translated.translated_excerpt == "Перевод"


@pytest.mark.asyncio
async def test_google_translate_failure_keeps_original(monkeypatch, document):
    class FailingGoogleClient:
        def __init__(self, **kwargs):
            assert kwargs == {"raise_exception": True}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return None

        async def translate(self, values, *, src, dest):
            raise RuntimeError("offline")

    monkeypatch.setattr("redline.services.Translator", FailingGoogleClient)

    assert await GoogleTranslator().document(document) == document


@pytest.mark.asyncio
async def test_initial_non_pheic_sync_does_not_alert_then_watch_update_does(
    tmp_path, document, event
):
    config = Config(initialized=True, watch_regions=["Rwanda"], translation_enabled=False)
    database = Database(tmp_path / "redline.sqlite3")
    service = SyncService(
        database,
        config,
        adapters=[FakeAdapter(document, event)],
        translator=GoogleTranslator(False),
        document_cache_root=tmp_path / "cache",
    )
    first = await service.sync(force=True)
    assert first[0].events_added == 1
    assert database.unread_alert_event_ids() == []
    document2 = replace(
        document, canonical_url=document.canonical_url + "-2", content_hash="document-hash-2"
    )
    event2 = replace(event, event_id="event-2", document_url=document2.canonical_url)
    service._adapters = [FakeAdapter(document2, event2)]
    second = await service.sync(force=True)
    assert second[0].alerts_added == 1
    assert database.unread_alert_event_ids() == ["event-2"]


@pytest.mark.asyncio
async def test_forced_sync_does_not_send_conditional_cache_headers(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    database.record_source_attempt(
        "who_don", success=True, etag="old-etag", last_modified="old-date"
    )
    adapter = FakeAdapter(document, event)
    service = SyncService(
        database,
        Config(initialized=True, translation_enabled=False),
        adapters=[adapter],
        translator=GoogleTranslator(False),
        document_cache_root=tmp_path / "cache",
    )

    await service.sync(force=True)

    assert adapter.fetch_headers == [(None, None)]


@pytest.mark.asyncio
async def test_startup_retry_bypasses_backoff_only_for_failed_source(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    database.record_source_attempt(
        "who_don",
        success=False,
        error="old adapter failure",
        next_due=utcnow() + timedelta(hours=1),
    )
    adapter = FakeAdapter(document, event)
    service = SyncService(
        database,
        Config(initialized=True, translation_enabled=False),
        adapters=[adapter],
        translator=GoogleTranslator(False),
        document_cache_root=tmp_path / "cache",
    )

    skipped = await service.sync()
    retried = await service.sync(retry_failed=True)

    assert skipped[0].skipped is True
    assert retried[0].fetched == 1
    assert adapter.fetch_headers == [(None, None)]


@pytest.mark.asyncio
async def test_startup_retry_does_not_fetch_sources_without_an_error(tmp_path, document, event):
    adapter = FakeAdapter(document, event)
    service = SyncService(
        Database(tmp_path / "redline.sqlite3"),
        Config(initialized=True, translation_enabled=False),
        adapters=[adapter],
        translator=GoogleTranslator(False),
        document_cache_root=tmp_path / "cache",
    )

    reports = await service.sync(retry_failed=True)

    assert reports == []
    assert adapter.fetch_headers == []
