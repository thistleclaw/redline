from __future__ import annotations

from dataclasses import replace

from redline.database import Database
from redline.reports import change_brief, who_guidance


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
