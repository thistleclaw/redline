from __future__ import annotations

import json
import re
from pathlib import Path

from redline.database import Database
from redline.i18n import tr

WHO_SOURCE_IDS = ("who_don", "who_sitreps", "who_hed", "who_blueprint")
GUIDANCE_PATTERN = re.compile(
    r"\b(?:recommend(?:s|ed|ation)?|advis(?:e|es|ed)|urges?|should|calls? on)\b", re.IGNORECASE
)


def change_brief(database: Database, *, limit: int = 8, language: str = "ru") -> str:
    events = database.events(limit=limit)
    unread = [row for row in events if row["unread_alert"]]
    lines = [tr(language, "brief.heading"), tr(language, "brief.notice")]
    if unread:
        lines.append(tr(language, "brief.alerts", count=len(unread)))
    if not events:
        lines.append(tr(language, "brief.empty"))
        return "\n".join(lines)
    for row in events:
        status = "ALERT" if row["unread_alert"] else str(row["evidence"]).upper()
        title = row["translated_title"] or row["title"] if language == "ru" else row["title"]
        territory = row["territory"] or tr(language, "field.unknown")
        lines.append(f"[{status}] {territory}: {title[:160]}")
    return "\n".join(lines)


def markdown_brief(
    database: Database, filters: dict[str, str] | None = None, *, language: str = "ru"
) -> str:
    events = database.events(limit=100, filters=filters)
    lines = [
        f"# REDLINE {tr(language, 'brief.heading').lower()}",
        "",
        f"> {tr(language, 'brief.notice')}",
        "",
    ]
    if not events:
        lines.append(tr(language, "events.empty").split("\n", 1)[0])
        return "\n".join(lines) + "\n"
    for row in events:
        title = row["translated_title"] or row["title"] if language == "ru" else row["title"]
        lines.extend(
            [
                f"## {title}",
                f"- Status: `{row['emergency']}` / `{row['evidence']}`",
                f"- Territory: {row['territory'] or 'not stated'}",
                f"- Source: {row['source_id']}",
                f"- Published: {row['published_at'] or 'not stated'}",
                f"- Original: {row['canonical_url']}",
                "",
            ]
        )
    return "\n".join(lines)


def who_guidance(database: Database, *, language: str = "ru", limit: int = 8) -> str:
    """Show attributed WHO sentences only; REDLINE does not synthesize recommendations."""
    lines = [tr(language, "who.heading"), tr(language, "who.notice"), ""]
    excerpts: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for document in database.documents(source_ids=WHO_SOURCE_IDS, limit=80):
        normalized = " ".join(str(document["original_text"] or document["excerpt"]).split())
        for sentence in re.split(r"(?<=[.!?])\s+", normalized):
            sentence = sentence.strip()
            if len(sentence) < 30 or not GUIDANCE_PATTERN.search(sentence):
                continue
            fingerprint = sentence.casefold()[:180]
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            excerpts.append((sentence[:420], document["title"], document["canonical_url"]))
            if len(excerpts) >= limit:
                break
        if len(excerpts) >= limit:
            break
    if not excerpts:
        lines.append(tr(language, "who.empty"))
        return "\n".join(lines)
    for index, (sentence, title, url) in enumerate(excerpts, 1):
        lines.extend([f"[{index}] {sentence}", f"WHO · {title}", url, ""])
    return "\n".join(lines).rstrip()


def write_export(
    database: Database,
    kind: str,
    target: Path,
    filters: dict[str, str] | None = None,
    *,
    language: str = "ru",
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if kind == "json":
        target.write_text(
            json.dumps(database.export_payload(filters), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    elif kind == "markdown":
        target.write_text(markdown_brief(database, filters, language=language), encoding="utf-8")
    else:
        raise ValueError("Поддерживаются только json и markdown.")
    return target
