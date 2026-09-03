from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import timedelta

from redline.database import Database
from redline.models import CountermeasureEvidence, EmergencyStatus, utcnow


def test_documents_are_versioned_events_keep_provenance(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    document_id, inserted = database.save_document(document)
    assert inserted
    assert database.save_event(event, document_id)
    assert not database.save_event(event, document_id)
    assert database.create_alert(event.event_id, "watch region")
    assert database.mark_alerts_read([event.event_id]) == 1
    row = database.events()[0]
    assert row["canonical_url"] == document.canonical_url
    assert row["disease_key"] == "ebola"
    assert database.document_for_event(event.event_id)["original_text"] == document.original_text


def test_event_moves_to_latest_immutable_document_version(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    first_id, _ = database.save_document(document)
    database.save_event(event, first_id)
    updated = replace(
        document, content_hash="document-hash-2", original_text="Updated official text"
    )
    second_id, inserted = database.save_document(updated)
    assert inserted and second_id != first_id
    database.save_event(event, second_id)
    assert database.document_for_event(event.event_id)["original_text"] == "Updated official text"
    assert (
        database.connection.execute(
            "SELECT count(*) FROM event_sources WHERE event_id = ?", (event.event_id,)
        ).fetchone()[0]
        == 2
    )


def test_retention_removes_old_cached_files_and_dependent_alerts(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    cache = tmp_path / "cached.txt"
    cache.write_text(document.original_text, encoding="utf-8")
    document_id, _ = database.save_document(document, str(cache))
    database.save_event(event, document_id)
    database.create_alert(event.event_id, "watch region")
    old = "2000-01-01T00:00:00+00:00"
    database.connection.execute("UPDATE events SET discovered_at = ?", (old,))
    database.connection.execute("UPDATE source_documents SET fetched_at = ?", (old,))
    database.connection.commit()
    result = database.prune(event_retention_days=365, document_cache_days=30)
    assert result["events"] == 1
    assert database.events() == []
    assert not cache.exists()
    assert database.connection.execute("SELECT count(*) FROM alerts").fetchone()[0] == 0


def test_source_error_keeps_last_success_for_stale_display(tmp_path):
    database = Database(tmp_path / "redline.sqlite3")
    database.record_source_attempt("who_don", success=True)
    database.record_source_attempt("who_don", success=False, error="timeout")
    state = database.source_health(stale_after=timedelta(days=1))[0]
    assert state.last_success is not None
    assert state.error == "timeout"
    assert not state.stale


def test_default_source_health_respects_its_own_next_due_and_grace(tmp_path):
    database = Database(tmp_path / "redline.sqlite3")
    now = utcnow()
    database.record_source_attempt(
        "who_blueprint", success=True, next_due=now + timedelta(hours=21)
    )
    database.connection.execute(
        "UPDATE source_state SET last_success = ? WHERE source_id = ?",
        ((now - timedelta(hours=3)).isoformat(), "who_blueprint"),
    )
    database.connection.commit()

    assert not database.source_health()[0].stale


def test_default_source_health_marks_source_stale_after_next_due_grace(tmp_path):
    database = Database(tmp_path / "redline.sqlite3")
    now = utcnow()
    database.record_source_attempt("who_don", success=True, next_due=now - timedelta(minutes=16))
    database.connection.execute(
        "UPDATE source_state SET last_success = ? WHERE source_id = ?",
        ((now - timedelta(minutes=30)).isoformat(), "who_don"),
    )
    database.connection.commit()

    assert database.source_health()[0].stale


def test_active_pheic_count_deduplicates_updates_and_uses_latest_explicit_state(
    tmp_path, document, event
):
    database = Database(tmp_path / "redline.sqlite3")
    first_id, _ = database.save_document(document)
    database.save_event(replace(event, emergency=EmergencyStatus.PHEIC), first_id)

    update_document = replace(
        document,
        canonical_url=document.canonical_url + "/update",
        content_hash="document-hash-update",
        published_at=document.published_at + timedelta(days=1),
    )
    update_id, _ = database.save_document(update_document)
    database.save_event(
        replace(
            event,
            event_id="event-update",
            document_url=update_document.canonical_url,
            situation_key="ebola|Rwanda|update",
            emergency=EmergencyStatus.PHEIC,
            occurred_at=update_document.published_at,
        ),
        update_id,
    )
    assert database.active_pheic_count() == 1

    ended_document = replace(
        document,
        canonical_url=document.canonical_url + "/ended",
        content_hash="document-hash-ended",
        published_at=document.published_at + timedelta(days=2),
    )
    ended_id, _ = database.save_document(ended_document)
    database.save_event(
        replace(
            event,
            event_id="event-ended",
            document_url=ended_document.canonical_url,
            situation_key="ebola|global|ended",
            emergency=EmergencyStatus.PHEIC_ENDED,
            occurred_at=ended_document.published_at,
        ),
        ended_id,
    )
    assert database.active_pheic_count() == 0


def test_countermeasure_evidence_is_normalized_deduplicated_and_exported(tmp_path, document):
    database = Database(tmp_path / "redline.sqlite3")
    rd_document = replace(
        document,
        source_id="who_blueprint",
        canonical_url="https://www.who.int/publications/m/item/filovirus-roadmap",
        content_hash="filovirus-roadmap",
        category="rd_blueprint",
    )
    document_id, _ = database.save_document(rd_document)
    evidence = CountermeasureEvidence(
        pathogen_key="filoviruses",
        pathogen_family="Filoviridae",
        kind="roadmap",
        label="Filovirus research and development roadmap",
        url=rd_document.canonical_url,
        status="published",
        published_at=rd_document.published_at,
        checked_at=rd_document.fetched_at,
    )

    assert database.save_countermeasure_evidence(evidence, document_id)
    assert not database.save_countermeasure_evidence(evidence, document_id)
    row = database.countermeasure_evidence("filoviruses")[0]

    assert row["pathogen_family"] == "Filoviridae"
    assert row["status"] == "published"
    assert database.export_payload()["countermeasure_evidence"][0]["url"] == evidence.url

    database.reconcile_countermeasure_evidence("who_blueprint", set())

    assert database.countermeasure_evidence("filoviruses") == []
    assert (
        database.connection.execute("SELECT active FROM countermeasure_evidence").fetchone()[0] == 0
    )


def test_history_query_limits_events_by_occurrence_time(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    document_id, _ = database.save_document(document)
    database.save_event(event, document_id)
    assert database.events(since=event.occurred_at - timedelta(days=1))
    assert database.events(since=event.occurred_at + timedelta(days=1)) == []


def test_obsolete_who_index_artifact_is_removed_on_reopen(tmp_path, document, event):
    path = tmp_path / "redline.sqlite3"
    database = Database(path)
    junk_document = replace(
        document,
        canonical_url="https://www.who.int/emergencies/disease-outbreak-news",
        title="Disease Outbreak News",
    )
    document_id, _ = database.save_document(junk_document)
    database.save_event(replace(event, document_url=junk_document.canonical_url), document_id)
    database.close()

    reopened = Database(path)

    assert reopened.events(filters={"source": "who_don"}) == []
    assert reopened.documents(source_ids=["who_don"]) == []


def test_existing_document_accepts_cleaned_metadata_without_changing_identity(tmp_path, document):
    database = Database(tmp_path / "redline.sqlite3")
    document_id, inserted = database.save_document(document)
    cleaned = replace(document, excerpt="Clean official summary")

    same_id, inserted_again = database.save_document(cleaned)

    assert same_id == document_id
    assert inserted and not inserted_again
    assert database.documents(source_ids=["who_don"])[0]["excerpt"] == "Clean official summary"


def test_existing_database_is_migrated_with_default_map_fields(tmp_path, document, event):
    path = tmp_path / "legacy.sqlite3"
    database = Database(path)
    database.close()
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE events DROP COLUMN map_status")
    connection.execute("ALTER TABLE events DROP COLUMN map_scope")
    connection.commit()
    connection.close()

    migrated = Database(path)
    document_id, _ = migrated.save_document(document)
    migrated.save_event(event, document_id)

    assert migrated.events()[0]["map_status"] == "outbreak"
    assert migrated.events()[0]["map_scope"] == "local"
