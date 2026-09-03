from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from redline.config import data_dir
from redline.models import (
    CountermeasureEvidence,
    Event,
    SourceDocument,
    SourceHealth,
    jsonable,
    utcnow,
)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Database:
    """SQLite store which keeps source documents immutable by URL and content hash."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_dir() / "redline.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._migrate()
        self._purge_known_index_artifacts()

    def close(self) -> None:
        self.connection.close()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_state (
                source_id TEXT PRIMARY KEY,
                last_success TEXT,
                last_attempt TEXT,
                error TEXT,
                etag TEXT,
                last_modified TEXT,
                next_due TEXT
            );
            CREATE TABLE IF NOT EXISTS source_documents (
                document_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                title TEXT NOT NULL,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                excerpt TEXT NOT NULL,
                original_text TEXT NOT NULL,
                translated_title TEXT,
                translated_excerpt TEXT,
                category TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                language TEXT NOT NULL,
                cached_path TEXT,
                UNIQUE(canonical_url, content_hash)
            );
            CREATE INDEX IF NOT EXISTS source_documents_url_idx
                ON source_documents(canonical_url);
            CREATE TABLE IF NOT EXISTS countermeasure_evidence (
                evidence_id TEXT PRIMARY KEY,
                source_document_id TEXT NOT NULL REFERENCES source_documents(document_id),
                source_id TEXT NOT NULL,
                pathogen_key TEXT NOT NULL,
                pathogen_family TEXT NOT NULL,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                published_at TEXT,
                last_seen TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(pathogen_key, kind, url)
            );
            CREATE INDEX IF NOT EXISTS countermeasure_pathogen_idx
                ON countermeasure_evidence(pathogen_key, kind, published_at DESC);
            CREATE TABLE IF NOT EXISTS situations (
                situation_key TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                disease_key TEXT,
                territory TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES source_documents(document_id),
                situation_key TEXT NOT NULL REFERENCES situations(situation_key),
                disease_key TEXT,
                disease_label TEXT,
                territory TEXT,
                latitude REAL,
                longitude REAL,
                location_precision TEXT NOT NULL,
                evidence TEXT NOT NULL,
                emergency TEXT NOT NULL,
                source_category TEXT NOT NULL,
                map_status TEXT NOT NULL DEFAULT 'outbreak',
                map_scope TEXT NOT NULL DEFAULT 'local',
                summary TEXT NOT NULL,
                occurred_at TEXT,
                discovered_at TEXT NOT NULL,
                UNIQUE(document_id, disease_key, territory)
            );
            CREATE INDEX IF NOT EXISTS events_situation_idx ON events(situation_key);
            CREATE TABLE IF NOT EXISTS event_sources (
                event_id TEXT NOT NULL REFERENCES events(event_id),
                document_id TEXT NOT NULL REFERENCES source_documents(document_id),
                linked_at TEXT NOT NULL,
                PRIMARY KEY(event_id, document_id)
            );
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(event_id),
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read_at TEXT
            );
            CREATE INDEX IF NOT EXISTS alerts_unread_idx ON alerts(read_at, created_at DESC);
            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                source_id TEXT,
                event_id TEXT,
                message TEXT NOT NULL,
                context_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        event_columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(events)").fetchall()
        }
        if "map_status" not in event_columns:
            self.connection.execute(
                "ALTER TABLE events ADD COLUMN map_status TEXT NOT NULL DEFAULT 'outbreak'"
            )
        if "map_scope" not in event_columns:
            self.connection.execute(
                "ALTER TABLE events ADD COLUMN map_scope TEXT NOT NULL DEFAULT 'local'"
            )
        evidence_columns = {
            row["name"]
            for row in self.connection.execute(
                "PRAGMA table_info(countermeasure_evidence)"
            ).fetchall()
        }
        if "active" not in evidence_columns:
            self.connection.execute(
                "ALTER TABLE countermeasure_evidence ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
            )
        self.connection.commit()

    def _purge_known_index_artifacts(self) -> None:
        """Remove events created by obsolete broad index-page parsing rules."""
        documents = self.connection.execute(
            """
            SELECT document_id FROM source_documents
            WHERE (source_id = 'who_don' AND canonical_url =
                   'https://www.who.int/emergencies/disease-outbreak-news')
               OR (source_id = 'ecdc_cdtr' AND canonical_url NOT LIKE
                   'https://www.ecdc.europa.eu/en/publications-data/communicable-disease-threats-report-%')
            """
        ).fetchall()
        document_ids = tuple(row["document_id"] for row in documents)
        if not document_ids:
            return
        placeholders = ",".join("?" for _ in document_ids)
        event_rows = self.connection.execute(
            f"SELECT event_id FROM events WHERE document_id IN ({placeholders})", document_ids
        ).fetchall()
        event_ids = tuple(row["event_id"] for row in event_rows)
        with self.connection:
            if event_ids:
                event_placeholders = ",".join("?" for _ in event_ids)
                self.connection.execute(
                    f"DELETE FROM alerts WHERE event_id IN ({event_placeholders})", event_ids
                )
                self.connection.execute(
                    f"DELETE FROM event_sources WHERE event_id IN ({event_placeholders})",
                    event_ids,
                )
                self.connection.execute(
                    f"DELETE FROM events WHERE event_id IN ({event_placeholders})", event_ids
                )
            self.connection.execute(
                f"DELETE FROM event_sources WHERE document_id IN ({placeholders})", document_ids
            )
            self.connection.execute(
                f"DELETE FROM source_documents WHERE document_id IN ({placeholders})", document_ids
            )
            self.connection.execute(
                "DELETE FROM situations WHERE situation_key NOT IN "
                "(SELECT DISTINCT situation_key FROM events)"
            )
            self.audit(
                "index_artifacts_purged",
                f"Removed {len(document_ids)} obsolete index document(s)",
            )

    @staticmethod
    def document_id(document: SourceDocument) -> str:
        return hashlib.sha256(
            f"{document.canonical_url}\n{document.content_hash}".encode()
        ).hexdigest()[:32]

    def source_seen(self, source_id: str) -> bool:
        row = self.connection.execute(
            "SELECT last_success FROM source_state WHERE source_id = ?", (source_id,)
        ).fetchone()
        return bool(row and row["last_success"])

    def source_headers(self, source_id: str) -> tuple[str | None, str | None]:
        row = self.connection.execute(
            "SELECT etag, last_modified FROM source_state WHERE source_id = ?", (source_id,)
        ).fetchone()
        return (row["etag"], row["last_modified"]) if row else (None, None)

    def record_source_attempt(
        self,
        source_id: str,
        *,
        success: bool,
        error: str | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
        next_due: datetime | None = None,
    ) -> None:
        now = utcnow()
        prior = self.connection.execute(
            "SELECT etag, last_modified FROM source_state WHERE source_id = ?", (source_id,)
        ).fetchone()
        self.connection.execute(
            """
            INSERT INTO source_state(source_id, last_success, last_attempt, error, etag, last_modified, next_due)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
              last_success = excluded.last_success,
              last_attempt = excluded.last_attempt,
              error = excluded.error,
              etag = excluded.etag,
              last_modified = excluded.last_modified,
              next_due = excluded.next_due
            """,
            (
                source_id,
                _iso(now) if success else self._source_last_success(source_id),
                _iso(now),
                error,
                etag if etag is not None else (prior["etag"] if prior else None),
                last_modified
                if last_modified is not None
                else (prior["last_modified"] if prior else None),
                _iso(next_due),
            ),
        )
        self.connection.commit()

    def _source_last_success(self, source_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT last_success FROM source_state WHERE source_id = ?", (source_id,)
        ).fetchone()
        return row["last_success"] if row else None

    def save_document(
        self, document: SourceDocument, cached_path: str | None = None
    ) -> tuple[str, bool]:
        document_id = self.document_id(document)
        existed = self.connection.execute(
            "SELECT 1 FROM source_documents WHERE document_id = ?", (document_id,)
        ).fetchone()
        if existed:
            # Content identity remains immutable, but adapters may learn better metadata (for
            # example an API publication date or a cleaned summary) on a later synchronization.
            self.connection.execute(
                """
                UPDATE source_documents SET
                  title = ?, published_at = COALESCE(?, published_at), excerpt = ?,
                  translated_title = COALESCE(?, translated_title),
                  translated_excerpt = COALESCE(?, translated_excerpt)
                WHERE document_id = ?
                """,
                (
                    document.title,
                    _iso(document.published_at),
                    document.excerpt,
                    document.translated_title,
                    document.translated_excerpt,
                    document_id,
                ),
            )
            self.connection.commit()
            return document_id, False
        self.connection.execute(
            """
            INSERT INTO source_documents(
              document_id, source_id, canonical_url, title, published_at, fetched_at, excerpt,
              original_text, translated_title, translated_excerpt, category, content_hash, language,
              cached_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                document.source_id,
                document.canonical_url,
                document.title,
                _iso(document.published_at),
                _iso(document.fetched_at),
                document.excerpt,
                document.original_text,
                document.translated_title,
                document.translated_excerpt,
                document.category,
                document.content_hash,
                document.language,
                cached_path,
            ),
        )
        self.connection.commit()
        return document_id, True

    def save_event(self, event: Event, document_id: str) -> bool:
        existing = self.connection.execute(
            "SELECT event_id FROM events WHERE event_id = ?", (event.event_id,)
        ).fetchone()
        now = _iso(utcnow())
        self.connection.execute(
            """
            INSERT INTO situations(situation_key, first_seen, last_seen, disease_key, territory)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(situation_key) DO UPDATE SET last_seen = excluded.last_seen
            """,
            (event.situation_key, now, now, event.disease_key, event.territory),
        )
        self.connection.execute(
            """
            INSERT INTO events(
              event_id, document_id, situation_key, disease_key, disease_label, territory,
              latitude, longitude, location_precision, evidence, emergency, source_category,
              map_status, map_scope, summary, occurred_at, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
              document_id = excluded.document_id,
              situation_key = excluded.situation_key,
              disease_key = excluded.disease_key,
              disease_label = excluded.disease_label,
              territory = excluded.territory,
              latitude = excluded.latitude,
              longitude = excluded.longitude,
              location_precision = excluded.location_precision,
              source_category = excluded.source_category,
              map_status = excluded.map_status,
              map_scope = excluded.map_scope,
              summary = excluded.summary,
              occurred_at = excluded.occurred_at,
              evidence = excluded.evidence,
              emergency = excluded.emergency
            """,
            (
                event.event_id,
                document_id,
                event.situation_key,
                event.disease_key,
                event.disease_label,
                event.territory,
                event.latitude,
                event.longitude,
                event.location_precision.value,
                event.evidence.value,
                event.emergency.value,
                event.source_category,
                event.map_status.value,
                event.map_scope.value,
                event.summary,
                _iso(event.occurred_at),
                _iso(event.discovered_at),
            ),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO event_sources(event_id, document_id, linked_at) VALUES (?, ?, ?)",
            (event.event_id, document_id, now),
        )
        self.connection.commit()
        return not bool(existing)

    def save_countermeasure_evidence(
        self, evidence: CountermeasureEvidence, document_id: str
    ) -> bool:
        evidence_id = self.countermeasure_evidence_id(evidence)
        existed = self.connection.execute(
            "SELECT 1 FROM countermeasure_evidence WHERE evidence_id = ?", (evidence_id,)
        ).fetchone()
        self.connection.execute(
            """
            INSERT INTO countermeasure_evidence(
              evidence_id, source_document_id, source_id, pathogen_key, pathogen_family,
              kind, label, url, status, published_at, last_seen, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(evidence_id) DO UPDATE SET
              source_document_id = excluded.source_document_id,
              pathogen_family = excluded.pathogen_family,
              label = excluded.label,
              status = excluded.status,
              published_at = COALESCE(excluded.published_at, published_at),
              last_seen = excluded.last_seen,
              active = 1
            """,
            (
                evidence_id,
                document_id,
                evidence.source_id,
                evidence.pathogen_key,
                evidence.pathogen_family,
                evidence.kind,
                evidence.label,
                evidence.url,
                evidence.status,
                _iso(evidence.published_at),
                _iso(evidence.checked_at),
            ),
        )
        self.connection.commit()
        return not bool(existed)

    @staticmethod
    def countermeasure_evidence_id(evidence: CountermeasureEvidence) -> str:
        return hashlib.sha256(
            f"{evidence.pathogen_key}|{evidence.kind}|{evidence.url}".encode()
        ).hexdigest()[:32]

    def reconcile_countermeasure_evidence(
        self, source_id: str, active_evidence_ids: set[str]
    ) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE countermeasure_evidence SET active = 0 WHERE source_id = ?",
                (source_id,),
            )
            if active_evidence_ids:
                placeholders = ",".join("?" for _ in active_evidence_ids)
                self.connection.execute(
                    f"UPDATE countermeasure_evidence SET active = 1 "
                    f"WHERE source_id = ? AND evidence_id IN ({placeholders})",
                    (source_id, *sorted(active_evidence_ids)),
                )

    def create_alert(self, event_id: str, reason: str) -> bool:
        existing = self.connection.execute(
            "SELECT 1 FROM alerts WHERE event_id = ? AND reason = ?", (event_id, reason)
        ).fetchone()
        if existing:
            return False
        created = utcnow()
        alert_id = hashlib.sha256(f"{event_id}\n{reason}".encode()).hexdigest()[:24]
        self.connection.execute(
            "INSERT INTO alerts(alert_id, event_id, reason, created_at) VALUES (?, ?, ?, ?)",
            (alert_id, event_id, reason, _iso(created)),
        )
        self.audit("alert_created", reason, event_id=event_id)
        self.connection.commit()
        return True

    def mark_alerts_read(self, event_ids: Iterable[str]) -> int:
        ids = tuple(event_ids)
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        result = self.connection.execute(
            f"UPDATE alerts SET read_at = ? WHERE read_at IS NULL AND event_id IN ({placeholders})",
            (_iso(utcnow()), *ids),
        )
        if result.rowcount:
            self.audit("alerts_read", f"Read {result.rowcount} alert(s)")
        self.connection.commit()
        return result.rowcount

    def audit(
        self,
        kind: str,
        message: str,
        *,
        source_id: str | None = None,
        event_id: str | None = None,
        context: dict | None = None,
    ) -> None:
        self.connection.execute(
            "INSERT INTO audit_log(created_at, kind, source_id, event_id, message, context_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                _iso(utcnow()),
                kind,
                source_id,
                event_id,
                message,
                json.dumps(context or {}, ensure_ascii=False),
            ),
        )

    def source_health(self, stale_after: timedelta | None = None) -> list[SourceHealth]:
        now = utcnow()
        rows = self.connection.execute("SELECT * FROM source_state ORDER BY source_id").fetchall()
        health: list[SourceHealth] = []
        for row in rows:
            last_success = _dt(row["last_success"])
            next_due = _dt(row["next_due"])
            if last_success is None:
                stale = True
            elif stale_after is not None:
                stale = now - last_success > stale_after
            elif next_due is not None:
                stale = now > next_due + timedelta(minutes=15)
            else:
                stale = now - last_success > timedelta(hours=2)
            health.append(
                SourceHealth(
                    source_id=row["source_id"],
                    last_success=last_success,
                    last_attempt=_dt(row["last_attempt"]),
                    error=row["error"],
                    stale=stale,
                    next_due=next_due,
                )
            )
        return health

    def active_pheic_count(self) -> int:
        """Count latest explicit PHEIC states by disease, independent of UI filters/history."""
        rows = self.connection.execute(
            """
            SELECT disease_key, situation_key, emergency
            FROM events
            WHERE emergency IN ('pheic', 'pheic_ended')
            ORDER BY COALESCE(occurred_at, discovered_at) DESC, discovered_at DESC
            """
        ).fetchall()
        latest: dict[str, str] = {}
        for row in rows:
            identity = str(row["disease_key"] or row["situation_key"])
            latest.setdefault(identity, str(row["emergency"]))
        return sum(status == "pheic" for status in latest.values())

    def events(
        self,
        *,
        limit: int = 100,
        filters: dict[str, str] | None = None,
        since: datetime | None = None,
    ) -> list[sqlite3.Row]:
        filters = filters or {}
        where: list[str] = []
        params: list[str | int] = []
        for field, column in {
            "source": "d.source_id",
            "disease": "e.disease_key",
            "region": "e.territory",
            "status": "e.evidence",
            "emergency": "e.emergency",
        }.items():
            if value := filters.get(field):
                where.append(f"LOWER({column}) LIKE ?")
                params.append(f"%{value.casefold()}%")
        if since:
            where.append("COALESCE(e.occurred_at, e.discovered_at) >= ?")
            params.append(_iso(since) or "")
        query = """
          SELECT e.*, d.source_id, d.canonical_url, d.title, d.published_at, d.excerpt,
                 d.translated_title, d.translated_excerpt,
                 EXISTS(SELECT 1 FROM alerts a WHERE a.event_id = e.event_id AND a.read_at IS NULL) AS unread_alert
          FROM events e JOIN source_documents d ON d.document_id = e.document_id
        """
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY COALESCE(e.occurred_at, e.discovered_at) DESC LIMIT ?"
        params.append(limit)
        return self.connection.execute(query, params).fetchall()

    def unread_alert_event_ids(self) -> list[str]:
        rows = self.connection.execute(
            "SELECT event_id FROM alerts WHERE read_at IS NULL"
        ).fetchall()
        return [row["event_id"] for row in rows]

    def document_for_event(self, event_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT d.* FROM source_documents d JOIN events e ON e.document_id = d.document_id
            WHERE e.event_id = ?
            """,
            (event_id,),
        ).fetchone()

    def documents(
        self, *, source_ids: Iterable[str] | None = None, limit: int = 100
    ) -> list[sqlite3.Row]:
        ids = tuple(source_ids or ())
        query = "SELECT * FROM source_documents"
        params: list[str | int] = []
        if ids:
            placeholders = ",".join("?" for _ in ids)
            query += f" WHERE source_id IN ({placeholders})"
            params.extend(ids)
        query += " ORDER BY COALESCE(published_at, fetched_at) DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        return self.connection.execute(query, params).fetchall()

    def countermeasure_evidence(self, pathogen_key: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT * FROM countermeasure_evidence
            WHERE pathogen_key = ? AND active = 1
            ORDER BY
              CASE kind
                WHEN 'roadmap' THEN 1
                WHEN 'prototype_pathogen' THEN 2
                WHEN 'diagnostics' THEN 3
                WHEN 'vaccines' THEN 4
                WHEN 'therapeutics' THEN 5
                WHEN 'clinical_protocols' THEN 6
                ELSE 7
              END,
              CASE status
                WHEN 'published' THEN 1
                WHEN 'in_development' THEN 2
                ELSE 3
              END,
              CASE WHEN published_at IS NULL THEN 1 ELSE 0 END,
              published_at DESC, last_seen DESC, label
            """,
            (pathogen_key,),
        ).fetchall()

    def all_countermeasure_evidence(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM countermeasure_evidence WHERE active = 1 "
            "ORDER BY pathogen_key, kind, COALESCE(published_at, last_seen) DESC"
        ).fetchall()

    def audit_entries(self, limit: int = 80) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM audit_log ORDER BY audit_id DESC LIMIT ?", (limit,)
        ).fetchall()

    def prune(self, *, event_retention_days: int, document_cache_days: int) -> dict[str, int]:
        event_before = _iso(utcnow() - timedelta(days=event_retention_days))
        doc_before = _iso(utcnow() - timedelta(days=document_cache_days))
        old_events = self.connection.execute(
            "SELECT event_id FROM events WHERE discovered_at < ?", (event_before,)
        ).fetchall()
        old_paths = self.connection.execute(
            "SELECT cached_path FROM source_documents WHERE fetched_at < ? AND cached_path IS NOT NULL",
            (doc_before,),
        ).fetchall()
        with self.connection:
            if old_events:
                placeholders = ",".join("?" for _ in old_events)
                event_ids = tuple(row["event_id"] for row in old_events)
                self.connection.execute(
                    f"DELETE FROM alerts WHERE event_id IN ({placeholders})", event_ids
                )
                self.connection.execute(
                    f"DELETE FROM event_sources WHERE event_id IN ({placeholders})", event_ids
                )
                event_result = self.connection.execute(
                    f"DELETE FROM events WHERE event_id IN ({placeholders})", event_ids
                )
            else:
                event_result = self.connection.execute("DELETE FROM events WHERE 1 = 0")
            cache_result = self.connection.execute(
                "UPDATE source_documents SET cached_path = NULL, original_text = excerpt WHERE fetched_at < ?",
                (doc_before,),
            )
            self.connection.execute(
                "DELETE FROM situations WHERE situation_key NOT IN (SELECT DISTINCT situation_key FROM events)"
            )
        for row in old_paths:
            try:
                Path(row["cached_path"]).unlink(missing_ok=True)
            except OSError:
                # Cache cleanup must never invalidate provenance retained in SQLite.
                pass
        self.audit(
            "retention_prune",
            "Retention cleanup",
            context={"events": event_result.rowcount, "documents": cache_result.rowcount},
        )
        self.connection.commit()
        return {"events": event_result.rowcount, "documents": cache_result.rowcount}

    def export_payload(self, filters: dict[str, str] | None = None) -> dict:
        events = [dict(row) for row in self.events(limit=1000, filters=filters)]
        return {
            "generated_at": _iso(utcnow()),
            "notice": "Informational monitor only. Not medical advice or a complete registry.",
            "events": jsonable(events),
            "sources": jsonable(self.source_health()),
            "countermeasure_evidence": jsonable(
                [dict(row) for row in self.all_countermeasure_evidence()]
            ),
        }
