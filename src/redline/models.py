from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC)


class LocationPrecision(StrEnum):
    POINT = "point"
    SUBREGION = "subregion"
    COUNTRY = "country"
    REGION = "region"
    UNKNOWN = "unknown"


class EvidenceStatus(StrEnum):
    CONFIRMED = "confirmed"
    POTENTIAL = "potential"
    REPORTED = "reported"
    UNKNOWN = "unknown"


class EmergencyStatus(StrEnum):
    NONE = "none"
    PHEIC = "pheic"
    PHEIC_ENDED = "pheic_ended"
    REGIONAL = "regional"


class MapStatus(StrEnum):
    OUTBREAK = "outbreak"
    SPREAD = "spread"
    EXTINCTION = "extinction"


class MapScope(StrEnum):
    LOCAL = "local"
    COUNTRY = "country"
    REGION = "region"
    CONTINENT = "continent"
    GLOBAL = "global"


@dataclass(frozen=True, slots=True)
class SourceDocument:
    source_id: str
    canonical_url: str
    title: str
    published_at: datetime | None
    fetched_at: datetime
    excerpt: str
    original_text: str
    category: str
    content_hash: str
    language: str = "en"
    translated_title: str | None = None
    translated_excerpt: str | None = None
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    document_url: str
    situation_key: str
    disease_key: str | None
    disease_label: str | None
    territory: str | None
    latitude: float | None
    longitude: float | None
    location_precision: LocationPrecision
    evidence: EvidenceStatus
    emergency: EmergencyStatus
    source_category: str
    summary: str
    occurred_at: datetime | None
    discovered_at: datetime = field(default_factory=utcnow)
    map_status: MapStatus = MapStatus.OUTBREAK
    map_scope: MapScope = MapScope.LOCAL


@dataclass(frozen=True, slots=True)
class CountermeasureEvidence:
    pathogen_key: str
    pathogen_family: str
    kind: str
    label: str
    url: str
    status: str
    published_at: datetime | None
    checked_at: datetime
    source_id: str = "who_blueprint"


@dataclass(frozen=True, slots=True)
class SourceHealth:
    source_id: str
    last_success: datetime | None
    last_attempt: datetime | None
    error: str | None
    stale: bool
    next_due: datetime | None


@dataclass(frozen=True, slots=True)
class Alert:
    alert_id: str
    event_id: str
    reason: str
    created_at: datetime
    read_at: datetime | None


def jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value
