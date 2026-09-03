from __future__ import annotations

from datetime import UTC, datetime

import pytest

from redline.models import (
    EmergencyStatus,
    Event,
    EvidenceStatus,
    LocationPrecision,
    SourceDocument,
)


@pytest.fixture
def document() -> SourceDocument:
    return SourceDocument(
        source_id="who_don",
        canonical_url="https://www.who.int/emergencies/disease-outbreak-news/item/test",
        title="Ebola outbreak confirmed in Rwanda",
        published_at=datetime(2026, 9, 1, tzinfo=UTC),
        fetched_at=datetime(2026, 9, 2, tzinfo=UTC),
        excerpt="A confirmed Ebola outbreak in Rwanda.",
        original_text="A confirmed Ebola outbreak in Rwanda. WHO published this official update.",
        category="who_don",
        content_hash="document-hash-1",
    )


@pytest.fixture
def event(document: SourceDocument) -> Event:
    return Event(
        event_id="event-1",
        document_url=document.canonical_url,
        situation_key="ebola|Rwanda|who_don",
        disease_key="ebola",
        disease_label="Ebola virus disease",
        territory="Rwanda",
        latitude=-1.94,
        longitude=29.87,
        location_precision=LocationPrecision.COUNTRY,
        evidence=EvidenceStatus.CONFIRMED,
        emergency=EmergencyStatus.NONE,
        source_category="who_don",
        summary=document.excerpt,
        occurred_at=document.published_at,
    )
