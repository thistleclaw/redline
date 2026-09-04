# REDLINE

**English** · [Русский](README.md)

![REDLINE synthetic spread demo](docs/screenshots/redline-spread.png)

REDLINE is a local-first epidemiological radar for Linux true-color terminals. It presents
official public-health sources as a Russian/English Textual TUI: a Braille world map,
event stream, source provenance, PHEIC status, R&D Blueprint context, a document viewer and
a persistent command line.

It is an information monitor, not medical advice, a forecast, or a complete event registry.
All alerts remain attributable to an official source. REDLINE does not send telemetry or
crash reports. When translation is enabled, document titles and excerpts are sent to Google
Translate through the lightweight, unofficial `googletrans` client; no translation model or
language package is downloaded. The original text and source attribution always remain available,
and a translation error or rate limit preserves the original English text. Gemini is contacted
only after an explicit AI command.

## Install

Python 3.10 or newer is required.

Install directly from GitHub:

```bash
pipx install 'git+https://github.com/thistleclaw/redline.git'
# or
uv tool install 'git+https://github.com/thistleclaw/redline.git'
```

For a local checkout:

```bash
pipx install .
# or
uv tool install .
```

For optional PDF text extraction:

```bash
pipx install '.[documents]'
```

Run `redline`. The first run opens a short local setup. Configuration is kept in
`~/.config/redline/config.toml`; SQLite data are kept in `~/.local/share/redline/`.
Run `redline --version` to verify which pipx build is installed.
On later launches REDLINE automatically checks sources in the background: due sources are
updated while fresh sources retain their individual polling intervals.
Set `translation_enabled = false` in the `[app]` section to keep all document text local and
show the English originals only.

Switch the complete interface immediately with `:language ru` or `:language en`. The choice is
saved to `config.toml`.

On a portrait Termux/mobile terminal the interface automatically places the map on top and the
Event Feed and Inspector side by side below it. Tap an event to select it, tap the Inspector or
command line to activate it, and swipe or use the mouse wheel to scroll a panel.

## Gemini setup

REDLINE uses Google's Gemini REST API directly. The primary model is
`gemini-3.5-flash-lite`; `gemini-3.1-flash-lite` is the fallback. The API key can be stored in
REDLINE's dedicated local secret file or supplied through an environment variable. It is never
written to the regular configuration, database or audit log.

The easiest persistent setup uses a hidden terminal prompt:

```bash
redline auth
```

The key is stored at `~/.config/redline/gemini.key`; the directory is mode `0700` and the key file
is mode `0600`. Inside the TUI, `:auth` opens a masked editor that can save or remove the same key
without restarting REDLINE. `redline auth --clear` removes it from the terminal. This is a local
plain-text secret protected by Unix file permissions, not an encrypted desktop keyring; processes
running as the same OS user can read it.

`GEMINI_API_KEY` and `GOOGLE_API_KEY` are also accepted and override the stored key. AI calls are
not scheduled in the background. An explicit AI command sends the active focus, filters, watch
regions, source health and up to 1,000 normalized events (including source URLs and summaries
capped at 700 characters) to Google. Cached complete documents, exports, the SQLite file, local
paths and audit entries are not sent.

## Commands

The bottom command line supports:

- `:exit` — close REDLINE cleanly.
- `:language <ru|en>` — switch and persist the interface language.
- `:auth` — securely save or remove the persistent Gemini API key using a masked field.
- `:ask ai <question>` — ask Gemini using the current monitor context.
- `:advice` — show attributed recommendation excerpts found in locally cached WHO documents; it
  does not invoke AI.
- `:advice ai` — ask Gemini for monitoring priorities and data-quality caveats based only on the
  monitor context. The result is explicitly labelled as AI analysis, not a WHO position or medical
  advice.
- `:forecast ai <bad|good>` — one command whose final argument selects a realistic adverse or
  favourable conditional scenario for the next 2–4 weeks and 1–3 months. It is explicitly labelled
  as an AI scenario, not a prediction or WHO forecast; baseline facts retain their source URLs.
- `:test` — enter an empty, isolated in-memory test database; synchronization is disabled there.
- `:test ai <scenario>` — ask Gemini to construct 3–12 explicitly synthetic events and display
  them on the map. Example: `:test ai глобальная эпидемия сибирской язвы в Евразии`.
- `:test ai timelapse <scenario>` — generate a synthetic progression up to 520 weeks and play it
  at one week per second. Add `duration=90d`, `duration=26w`, `duration=18m` or `duration=3y` and
  `speed=2w/s` or `speed=1w/2s` after `timelapse`; duration and speed may appear in either order.
- `:test pause`, `:test play`, `:test step` — pause, resume, or advance a timelapse by one week.
- `:test off` — discard all test events and restore the untouched live database and view state.
- `:focus`, `:filter`, `:sync`, `:history`, `:brief`, `:export`, `:log`, `:settings` — existing
  navigation, synchronization and reporting commands.

Enter `:help` in the TUI for the localized command reference.

`PgUp` and `PgDown` move cyclically through the event feed, inspector, and command line;
the active field has a `▶` marker. In the feed and inspector, `Up` and `Down` navigate or
scroll the active content. In the command line, `Up` and `Down` browse persistent command
history (the last 200 commands, stored locally with owner-only permissions).
In the feed, `Up` and `Down` move between events. In the inspector, the same keys scroll long text
one line at a time. Commands and opened documents automatically select the inspector.

## Sources

REDLINE only contacts enabled, allow-listed official sources: WHO Disease Outbreak News,
WHO situation reports and Health Emergency Dashboard, CDC Outbreaks, ECDC CDTR, PAHO
epidemiological alerts, Africa CDC event-based surveillance reports, and WHO R&D Blueprint
pages. Source-specific freshness and errors are visible in the TUI.

The WHO R&D Blueprint adapter maintains a separate countermeasure-evidence layer. An outbreak with
a curated pathogen alias is linked to its WHO-2024 pathogen family and prototype pathogen, then to
the latest synchronized roadmap, diagnostic, vaccine, therapeutic and clinical-protocol documents.
Publication date and REDLINE's last-check date are shown separately. Missing categories remain `—`;
REDLINE never converts a passing mention inside a roadmap into product evidence and calculates no
readiness score. Run `:sync who_blueprint` to refresh this layer.

Generic extraction is deliberately conservative and sentence-scoped. A bare mention of PHEIC or
the word “confirmed” is not sufficient: explicit current assertions are required, while negated,
ended, and clearly historical statements are handled separately. Disease aliases require token
boundaries. Country and city resolution uses an offline GeoNames-derived gazetteer with alternate
names; watch regions compare geographic identities instead of arbitrary substrings.

Freshness follows each source's own `next_due` plus a grace period, rather than a universal
two-hour timeout. The top-line `PHEIC: N` is independent of UI filters and history windows: it
deduplicates updates and uses the latest explicit active/ended state for each disease.

PAHO's Pantheon frontend may reject the normal `httpx` transport with HTTP 403. The PAHO adapter
then retries the same official allow-listed index and document pages through Python's proxy-free
standard HTTPS transport, validates every final redirect target, caps index responses at 5 MB and
keeps clean canonical `paho.org/en/documents/...` URLs. No proxy, mirror or third-party feed is used.

The WHO DON adapter resolves the JavaScript index through WHO's official OData endpoint and then
fetches each canonical DON page. Page metadata supplies the concise inspector summary; navigation,
headers, forms and footers are excluded. ECDC ingestion accepts only canonical weekly CDTR report
paths and treats each CDTR as a multi-threat regional report rather than inventing a point outbreak.

The Health Emergency Dashboard and Disease Outbreak News are explicitly marked as
non-exhaustive in the interface. Full documents are cached locally for 30 days only; event
metadata and provenance are retained for 12 months by default.

The Braille coastline uses the pinned Natural Earth 1:110m land dataset (v5.1.2). Natural
Earth map data are public domain. The base geography is rendered in cobalt; geolocated outbreak
events are separate Braille layers. Bright red is a local outbreak. Synthetic spread stages fill
the affected land area in progressively darker red at country, region, continent and global scale.
Grey fills only affected land for an explicit human-population extinction stage; global extinction
greys the world's landmasses instead of drawing a point or a square. Global dashboards,
worldwide context pages, unknown locations, R&D context and broad risk-assessment reports never
become map markers. REDLINE does not infer extinction from official reports.

Country and city names and coordinates are supplied locally by `geonamescache`, derived from
[GeoNames](https://www.geonames.org/) data under CC BY 4.0. REDLINE makes no runtime requests to
the GeoNames service.
