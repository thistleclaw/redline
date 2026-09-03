# REDLINE architecture

## Trust boundary

REDLINE has no telemetry and does not ingest social, media, preprint, or aggregator feeds.
`SourceSpec.allowed_hosts` is an explicit HTTPS allow-list. Source adapters use public landing
pages or RSS, do not follow redirects by default, preserve the original canonical URL, and expose
a source error instead of silently switching to a third-party mirror. PAHO's restricted frontend
uses a dedicated fallback that validates the final redirect host against the same allow-list.
Translation is one explicit
operator-controlled exception: when enabled, the `googletrans` client sends only document titles
and excerpts to Google Translate. Explicit `:ask ai`, `:advice ai`, and `:test ai` commands are the
other exception and call the Google Gemini REST API. Neither integration uploads the SQLite file,
cached complete documents, exports, audit entries, or local paths.

The Gemini client resolves credentials in this order: an explicitly injected key,
`GEMINI_API_KEY`, `GOOGLE_API_KEY`, then the local `~/.config/redline/gemini.key` secret. The
persistent secret is written atomically inside a mode-`0700` directory as a mode-`0600` regular
file; symlinked or foreign-owned key files are rejected. Keys never enter `config.toml`, SQLite or
the audit log. The client disables environment-derived proxies and redirects. The model chain is
`gemini-3.5-flash-lite` followed by `gemini-3.1-flash-lite`. Normal AI requests serialize at most
1,000 normalized events with 700-character summaries, source URLs, source health, active filters,
focus and watch regions. Source text is marked as untrusted data in the system instruction to limit
prompt-injection risk. Only request purpose and successful model name enter the audit log; prompts,
contexts, and answers do not.

`SourceDocument` versions are immutable by canonical URL plus content hash. `EventSource` links
retain each source document even when deterministic aliases group documents into a `Situation`.
The model never calculates a disease-risk score. Red alerts represent either a PHEIC or a new,
official confirmed alert in a configured watch-region.

Generic event extraction is sentence-scoped to the title and concise official metadata. PHEIC,
regional-emergency, confirmed-case and potential-case states require explicit assertion patterns;
negated, ended and clearly historical statements are classified separately. Disease aliases use
token boundaries. This is intentionally a conservative deterministic parser, not unrestricted NLP,
and the primary source remains the authority whenever wording is ambiguous.

Locations are resolved locally through the pinned `geonamescache` dependency (GeoNames-derived
countries, cities and alternate names). Resolved watch regions compare stable geographic identity
and country containment; substring fallback is used only when one side cannot be resolved. Generic
three-letter country codes are excluded because normal prose such as “can” would otherwise produce
false coordinates.

## Local lifecycle

- `~/.config/redline/config.toml`: operator-owned configuration.
- `~/.local/share/redline/redline.sqlite3`: events, sources, alerts, audit trail.
- `~/.cache/redline/documents`: source text cache, purged after 30 days.

The scheduler wakes every 15 minutes. Each source has its own lower poll limit, ETag and
Last-Modified state. A failed source keeps its last-good data. Freshness is evaluated against that
source's stored `next_due` plus a scheduler-sized 15-minute grace period, so a healthy daily or
weekly source does not become stale before it was due to run.

The top-line PHEIC counter is database state, not presentation state. It considers only explicit
PHEIC declarations and explicit ended states, takes the latest such state per disease and therefore
does not change when the operator filters the feed or changes the history window.

WHO DON is a JavaScript-rendered index. Its adapter queries WHO's own allow-listed OData endpoint
for canonical DON identifiers, then downloads the corresponding WHO pages. A page's official
description metadata becomes the event summary while the cleaned article remains available to the
viewer. ECDC candidate paths are limited to weekly CDTR publications; a CDTR remains a multi-threat
regional report and therefore does not create a guessed disease/location marker.

## Map layers

The base layer is a pinned Natural Earth v5.1.2 physical-land dataset at 1:110m, rendered as
one-dot cobalt coastlines. Longitude and latitude use a single scale in the terminal's 2x4 Braille
pixel grid, so resizing letterboxes the map instead of stretching continents. Bright-red five-dot
marks represent local outbreaks. Synthetic spread and extinction events carry an explicit
`local/country/region/continent/global` map scope: spread fills affected land with graduated dark
red, while extinction fills affected land in grey. Area layers are clipped to rasterized land
polygons; a global extinction stage covers all land rather than drawing a marker around an
arbitrary coordinate. R&D context and generic source landing pages are never plotted as outbreaks.

## Viewer and translation

The viewer renders saved plain text only. PDF extraction is optional and local. English-to-Russian
translation uses the lightweight, unofficial online `googletrans` client during synchronization; it
downloads no language model or package. Translation failures, rate limits and offline operation
leave the English original unchanged. Original text, publisher, date and URL remain visible.

## Advice and test isolation

`:advice` is deterministic: it extracts explicitly worded recommendation sentences only from
locally stored WHO documents and retains title and URL attribution. It never fabricates guidance.
`:advice ai` is visibly labelled as AI analysis and its system instruction forbids presenting the
answer as WHO guidance, diagnosis, treatment or prediction.

Test mode replaces the active database and viewer with an SQLite `:memory:` database. Scheduled and
manual source synchronization are disabled until `:test off`. Gemini-created events use
`redline-test://` provenance, a dedicated synthetic source id and visible synthetic labels. Leaving
test mode closes and discards the temporary database, then restores the live database, filters,
focus, history window and selection.

An AI timelapse is also memory-only. REDLINE accepts 6–40 validated synthetic events with integer
week offsets over a duration of up to 520 weeks. The prompt requests 12–40 events and, for
timelines longer than one year, 24–40 events distributed across early, middle and late stages.
The UI reveals due events
on a Textual timer (default `1w/1s`), supports `pause`, `play` and single-week `step`, and stops the
timer before discarding the test database. REDLINE validates the 40-event cap locally rather than
sending the large array maximum rejected by the Flash-Lite structured-schema endpoint.
