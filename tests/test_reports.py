from __future__ import annotations

from dataclasses import replace

from redline.database import Database
from redline.models import CountermeasureEvidence
from redline.reports import change_brief, markdown_brief, who_guidance


def test_who_advice_contains_only_attributed_local_who_guidance(tmp_path, document):
    database = Database(tmp_path / "redline.sqlite3")
    guidance = replace(
        document,
        original_text="WHO recommends enhanced surveillance in affected districts.",
        content_hash="who-guidance",
    )
    database.save_document(guidance)

    report = who_guidance(database, language="en")

    assert "WHO recommends enhanced surveillance" in report
    assert document.canonical_url in report
    assert "ATTRIBUTED GUIDANCE" in report


def test_change_brief_is_localized(tmp_path):
    database = Database(tmp_path / "redline.sqlite3")

    assert "СВОДКА ИЗМЕНЕНИЙ" in change_brief(database, language="ru")
    assert "CHANGE BRIEF" in change_brief(database, language="en")


def test_markdown_export_links_event_to_blueprint_profile(tmp_path, document, event):
    database = Database(tmp_path / "redline.sqlite3")
    event_document_id, _ = database.save_document(document)
    database.save_event(event, event_document_id)
    rd_document = replace(
        document,
        source_id="who_blueprint",
        canonical_url="https://www.who.int/publications/m/item/filovirus-roadmap",
        content_hash="filovirus-roadmap",
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

    report = markdown_brief(database, language="en")

    assert "R&D family: Filoviridae" in report
    assert "Prototype pathogen: Orthoebolavirus zairense" in report
    assert "[Filovirus R&D roadmap]" in report
