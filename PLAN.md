# Shabla Events — Local News-to-Events Pipeline

## Context

The user lives in Shabla, Bulgaria and struggles to find out what local events (concerts, festivals, exhibitions, municipal announcements) are happening nearby, because coverage is scattered across many small local and regional publications with no unified calendar. The goal is a fully automated, zero-recurring-cost pipeline that scrapes these publications daily, uses an LLM to extract structured event data, and publishes it as a public, browsable page — solving a real personal information-discovery problem without requiring the user to check a dozen different sites manually.

This plan is the product of an extended design conversation in which every major architectural choice was deliberately made (not defaulted) by the user, including a cost-minimization constraint (self-hosted open-source LLM, no paid APIs, no paid hosting) and a data-quality constraint modeled on the user's professional experience with AML adverse-media relevancy scoring (a cheap pre-filter before expensive processing, plus per-source relevancy/pass-rate tracking).

**New, separate repository** at `C:\Users\Bryant\source\repos\shabla-events` — intentionally not part of the existing `bryantasprilla.github.io` repo, which remains untouched.

## Locked architecture decisions

- **Hosting/cost**: $0 recurring cost. GitHub Actions (daily cron) does all scraping/processing; GitHub Pages (same repo) serves the public static UI. No server, no hosted DB, no paid APIs.
- **Repo visibility**: public (required for free GitHub Pages + unlimited free Actions minutes on a personal account). Both the events page and the stats/health dashboard are public — nothing in either is sensitive.
- **Storage**: a single SQLite database file, committed to the repo after each run.
- **LLM**: self-hosted, open-source **Qwen2.5-7B-Instruct** (GGUF, Q4_K_M quantization), run via `llama-cpp-python` bindings directly inside the GitHub Actions runner (CPU inference). Model weights cached across runs via `actions/cache`. Output forced into a strict JSON schema via **GBNF grammar-constrained decoding**, so a smaller model can't produce malformed output.
- **Sources**: ~20 sources across 6 tiers, covering everything within roughly a 2-hour drive of Shabla, spanning both sides of the Bulgaria-Romania border (Shabla itself → Kavarna/Balchik → Dobrich region → Varna → edge of Silistra region → southeastern Romania, Constanța and the coast south of it toward the border). Full list in `sources.yaml` (section 3 below). All sources — including already-structured event-calendar sites like visit.varna.bg and Romania's OnEvent.ro/ZileSiNopti.ro — go through the **same** pipeline ending in one LLM extraction step, per the user's explicit decision that the LLM should be the single point of schema normalization.
- **Bilingual content**: sources now span Bulgarian and Romanian. The relevance filter's keyword and geo-tag lists carry both-language terms (a term list is just OR-matched, so extra terms from the other language don't hurt scoring), and the LLM prompt/extraction step must handle either language article text.
- **Event categories**: the schema's `category` enum includes an explicit `adult_18+` value (nightlife/adult-oriented or NSFW-themed events — e.g. club parties, adult venues, age-restricted festival programming), distinct from general `festival`/`concert`, so these are tagged rather than dropped into `other` or filtered out.
- **Admin/source management**: no hosted admin UI (avoids needing auth infrastructure). `sources.yaml` is the single source of truth; a `manage.py` CLI adds/removes/validates sources and can dry-run test-fetch a candidate URL before it's committed. Git push access = admin access.
- **Error handling**: every source's scrape is isolated (try/except) so one broken site never blocks the others. Failures are logged; a source failing N consecutive runs (default 3, overridable per-source) auto-files a GitHub Issue via the Actions job's built-in token, and auto-closes it on the next success.
- **Relevance filtering** (cost-minimization pre-screen, analogous to the user's AML relevancy-score workflow): cheap SQLite FTS5 + BM25 keyword scoring, a Bulgarian date/time regex bonus, and a geo place-name gate — run **before** anything reaches the LLM. This is what keeps Varna's high-volume general news from flooding the expensive extraction step.
- **Stats tracking**: every article's journey through the pipeline (fetched → passed change-detection → passed relevance filter → confirmed event) is logged per source, producing a rolling pass-rate metric per source, exported to `source_stats.json` and shown on a public stats page.

## Repo structure

```
shabla-events/
├── .github/workflows/daily.yml
├── data/shabla_events.db              # committed SQLite DB
├── docs/                              # GitHub Pages source (Settings -> Pages -> main /docs)
│   ├── index.html                     # public events page
│   ├── stats.html                     # public health/stats dashboard
│   ├── events.json                    # generated export, overwritten each run
│   ├── source_stats.json              # generated export, overwritten each run
│   └── assets/{app.js,stats.js,style.css}
├── pipeline/
│   ├── config.py                      # loads sources.yaml + settings
│   ├── db.py                          # schema init (idempotent), connection helper
│   ├── fetchers/{base.py,rss.py,html_generic.py}
│   ├── hashing.py                     # change-detection hashing
│   ├── geo.py                         # canonical place-name list + matcher
│   ├── relevance.py                   # FTS5 + BM25 + regex + geo gate
│   ├── llm/{prompt.py,grammar.gbnf,extractor.py}
│   ├── dedup.py                       # cross-source near-duplicate merge
│   ├── export.py                      # writes docs/events.json, docs/source_stats.json
│   ├── issues.py                      # GitHub Issue open/update/close via REST API
│   └── run.py                         # orchestrator entrypoint
├── manage.py                          # admin CLI
├── sources.yaml
├── models/                            # gitignored; populated by actions/cache + curl
├── tests/
├── requirements.txt
├── .gitignore
└── README.md
```

Pages are served from `/docs` on `main` — the daily commit that updates the JSON exports *is* the deploy, no separate deploy action needed.

## Database schema (SQLite DDL)

```sql
CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT,
    body            TEXT,
    published_at    TEXT,
    fetched_at      TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'new',
        -- new | filtered_out | sent_to_llm | event_confirmed | not_event | error
    relevance_score REAL,
    geo_matched     TEXT,               -- JSON array of matched geo tags
    llm_raw_response TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_id, url)
);
CREATE INDEX IF NOT EXISTS idx_articles_source_status ON articles(source_id, status);

CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title, body, content='articles', content_rowid='id'
);
-- triggers articles_ai / articles_ad / articles_au keep articles_fts in sync on insert/delete/update

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    event_date      TEXT,               -- YYYY-MM-DD, nullable
    event_time      TEXT,               -- HH:MM, nullable
    location        TEXT,
    category        TEXT,               -- concert|festival|exhibition|municipal|sports|theater|adult_18+|other
    description     TEXT,
    dedup_key       TEXT,
    status          TEXT NOT NULL DEFAULT 'active',   -- active | past | merged
    merged_into     INTEGER REFERENCES events(id),
    first_confirmed_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_date_status ON events(event_date, status);

CREATE TABLE IF NOT EXISTS event_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER NOT NULL REFERENCES events(id),
    article_id      INTEGER NOT NULL REFERENCES articles(id),
    source_id       TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    UNIQUE(event_id, article_id)
);

CREATE TABLE IF NOT EXISTS source_runs (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id                TEXT NOT NULL,
    run_at                   TEXT NOT NULL DEFAULT (datetime('now')),
    status                   TEXT NOT NULL,     -- success | error | partial
    http_status              INTEGER,
    error_message            TEXT,
    articles_fetched         INTEGER DEFAULT 0,
    articles_new_or_changed  INTEGER DEFAULT 0,
    articles_passed_filter   INTEGER DEFAULT 0,
    events_confirmed         INTEGER DEFAULT 0,
    duration_ms              INTEGER
);
CREATE INDEX IF NOT EXISTS idx_source_runs_source_time ON source_runs(source_id, run_at);

CREATE TABLE IF NOT EXISTS source_issues (
    source_id           TEXT PRIMARY KEY,
    github_issue_number INTEGER,
    opened_at           TEXT,
    last_commented_at   TEXT,
    resolved_at          TEXT
);
```

`db.py` runs all `CREATE ... IF NOT EXISTS` statements at the start of every run — the entire migration story at this scale.

## `sources.yaml`

Fields per source: `id`, `name`, `tier` (1-5), `type` (`rss` | `html-article-list` | `structured-calendar`), `url`, `active`, `geo_tags`, `assume_in_range` (skip per-item geo gate for inherently-local sources), `skip_keyword_filter` (true for structured-calendar sources — every entry is already an event), `selectors` (for html/calendar types), optional per-source `consecutive_failure_threshold` override.

Initial source list:

| Tier | Source | URL | type | assume_in_range |
|---|---|---|---|---|
| 1 | Shabla municipality — Events | shabla.bg/aktualno/sabitiya/ | html-article-list | true |
| 1 | Shabla municipality — News | shabla.bg/aktualno/novini/ | html-article-list | true |
| 1 | NCh "Zora 1894" (cultural center) | nch-zora1894shabla.com/novini/ | html-article-list | true |
| 2 | Kavarna municipality | kavarna.bg/novini-aktualno-sybitiya | html-article-list / rss | true |
| 2 | Balchik municipality | balchik.bg | html-article-list | true |
| 3 | Dobrich.media (Shabla category) | dobrich.media/category/regionalni/obshtinashabla/ | html-article-list | true |
| 3 | ProNews Dobrich | pronewsdobrich.bg | html-article-list | false (geo gate applies) |
| 3 | Dobrich Online | dobrichonline.com | html-article-list | false |
| 3 | Dobrudzha news agency | dobrudjabg.com | html-article-list | false |
| 4 | Visit Varna event calendar | visit.varna.bg/bg/event.html | structured-calendar | false, skip_keyword_filter: true |
| 4 | Varna Culture calendar | varnaculture.bg | structured-calendar | false, skip_keyword_filter: true |
| 4 | Budna Varna | budnavarna.com | html-article-list | false |
| 4 | Moreto.net (Varna events) | moreto.net/events.php | html-article-list | false |
| 5 | Portal Silistra | portal-silistra.eu | html-article-list | false |
| 5 | Silistra News | silistranews.net | html-article-list | false |
| 6 | MangaliaNews.ro (Events category) | mangalianews.ro/category/evenimente/ | html-article-list | true |
| 6 | Mangalia.TV | mangalia.tv | html-article-list | true |
| 6 | Cuget Liber (Mangalia) | cugetliber.ro/mangalia | html-article-list | true |
| 6 | Ziua de Constanța | ziuaconstanta.ro/stiri.html | html-article-list | false |
| 6 | OnEvent.ro (Constanța) | onevent.ro/orase/constanta/ | structured-calendar | false, skip_keyword_filter: true |
| 6 | Zile și Nopți (Constanța) | zilesinopti.ro/evenimente-constanta/ | structured-calendar | false, skip_keyword_filter: true |

Tier 6 covers southeastern Romania — Constanța and the coast south of it toward the border (Mamaia, Eforie, Costinești, 2 Mai, Vama Veche, Mangalia, Limanu) — which is geographically as close to Shabla as Kavarna, just across the border. `assume_in_range: true` sources are Mangalia-area outlets covering exactly that stretch of coast; Constanța-city sources need the geo gate since Constanța itself is a full city with plenty of unrelated news. Note `zilesinopti.ro` ("Days and Nights") is a nightlife/party-agenda site — a natural source of `adult_18+`-category events.

`manage.py validate` enforces unique ids/urls, valid enums, required selectors, and warns (doesn't hard-fail) on unrecognized `geo_tags`.

## `manage.py` CLI

- `list-sources [--tier N] [--type ...] [--active-only] [--format table|json]`
- `validate` — schema + duplicate + geo-tag checks with line-referenced errors
- `test-source SOURCE_ID` — dry-run fetch using the real fetcher code, prints HTTP status, item count, sample parsed items, selector-miss warnings; writes nothing
- `add-source --id --name --url --tier --type [--geo-tags] [--assume-in-range] [--skip-keyword-filter] [--selectors-json] [--inactive] [--dry-run] [--yes]` — **always** runs the same dry-run test-fetch first and shows the sample before writing anything to `sources.yaml`; prompts for confirmation unless `--yes`
- `remove-source --id [--yes]` — removes the YAML entry only; historical DB rows are kept
- `activate-source` / `deactivate-source` — toggle without deleting config (the recommended first response to a filed error issue)
- `show-stats --source-id ID [--days N]` — reads the local committed DB and prints the same pass-rate summary as the public stats page, for fast local debugging

YAML read/write via `ruamel.yaml` to preserve comments/formatting in the hand-maintained config file.

## Relevance filter

- **FTS5 + BM25**: keyword list combines Bulgarian event-indicating terms (събитие, концерт, изложба, фестивал, ще се проведе, заповядайте, читалище, тържество, etc.) and Romanian equivalents (eveniment, concert, festival, petrecere, expoziție, spectacol, se va desfășura, etc.) in one list — FTS5 MATCH is just OR-boolean, so a Bulgarian article simply won't hit the Romanian terms and vice versa, no per-source language switch needed. Title weighted above body via `bm25(articles_fts, 5.0, 1.0)`. SQLite's bm25 returns more-negative-is-better; negate it so higher-is-better holds everywhere in the code.
- **Date/time regex bonus**: Bulgarian and Romanian month names, `DD.MM.YYYY`, `HH:MM ч.`/`ora HH:MM`, weekday names in both languages — a match adds a fixed bonus to the normalized score before thresholding.
- **Geo gate** (`geo.py`): canonical place list now spans both countries — Shabla, Durankulak, Krapets, Tyulenovo, Kavarna, Balchik, Dobrich, General Toshevo, Tervel, Varna, Silistra, Dulovo, Tutrakan (Bulgarian side) plus Constanța, Mamaia, Eforie, Costinești, 2 Mai, Vama Veche, Mangalia, Limanu (Romanian side), each with inflected/declined variants in its own language — matched case-insensitively against title+body; records matched tags into `articles.geo_matched`.
- **Combined decision**: `assume_in_range` sources skip the geo gate; `skip_keyword_filter` sources (structured calendars) skip the keyword gate but still need a geo match. Regional news sources (Tier 3/4 non-calendar) must pass both — this is specifically what prevents Varna's volume of unrelated city news from reaching the LLM.
- Every article's `relevance_score` and `geo_matched` are persisted regardless of outcome, so thresholds can be calibrated later by reviewing near-misses without re-fetching.

## LLM extraction

- **Runtime**: `llama-cpp-python` bindings (not shelling out to a CLI binary) — enables direct `LlamaGrammar` use, one model load reused across all of a run's articles, and clean Python exception handling.
- **Prompt**: system message defines the extraction task, notes the article may be in **Bulgarian or Romanian**, and the "not an event" fallback; also instructs the model to use the `adult_18+` category for nightlife/adult-oriented or age-restricted events rather than defaulting to `other`. User message includes source name/URL, article title/body (truncated to a fixed token budget), and **today's date** (needed to resolve relative date phrases like "утре"/"mâine").
- **Output schema**: `{is_event, title, date, time, location, category, description, source_url}`. `source_url` is always overwritten with the known `article.url` after parsing — never trust the model to faithfully reproduce a URL.
- **GBNF grammar** (`pipeline/llm/grammar.gbnf`) enforces the exact key set, `is_event` as a JSON bool, `date` as `""` or strict `YYYY-MM-DD`, `time` as `""` or strict `HH:MM`, `category` as a fixed enum (`concert|festival|exhibition|municipal|sports|theater|adult_18+|other`), and ordinary JSON strings elsewhere — makes malformed JSON structurally impossible, so no retry/repair logic is needed.
- **Multilingual risk flag**: Qwen2.5-7B-Instruct has reasonable Romanian coverage alongside Bulgarian, but both are comparatively lower-resource languages for a 7B model — Milestone 7/12 fixtures should include Romanian event/non-event examples (not just Bulgarian) so extraction quality on the new Tier 6 sources is verified, not assumed.
- **Model caching**: `actions/cache` keyed on `qwen2.5-7b-instruct-q4_k_m-v1`; download from Hugging Face only on a cache miss. GitHub's cache evicts after 7 days of disuse, but a daily job touches it every run so it never goes stale.
- **Risk flags to verify early**: confirm `llama-cpp-python` has a prebuilt wheel for `ubuntu-latest` at the pinned version (avoid a slow from-source build every run); expect roughly 10-40s per article on CPU, fine for expected daily volume but `run.py` should log `articles_passed_filter` per run so a sudden spike signals a relevance-filter regression rather than silently just taking longer.

## Cross-source dedup (`dedup.py`)

1. Normalize the confirmed event's title (lowercase, strip diacritics/punctuation) as a candidate key.
2. Look up existing `active` events with an `event_date` exact match or within ±1 day (or where either side lacks a date).
3. Score candidates: title similarity via `rapidfuzz` (threshold ≥85/100 starting point), location match (exact string or same resolved `geo_tag`), and date compatibility (never merge if both have dates that clearly differ beyond the window — protects recurring annual events from collapsing into each other).
4. On merge: link the new article via `event_sources` to the existing canonical event; backfill any missing canonical fields from the new source, prefer the longer description.
5. No match: insert a new canonical `events` row.

## GitHub Actions workflow (`.github/workflows/daily.yml`)

- Triggers: daily cron (confirm desired Sofia local time before launch) + `workflow_dispatch` for manual runs.
- Permissions: `contents: write`, `issues: write`.
- Steps: checkout → setup Python → cache pip packages → install deps → cache model weights → download model on cache miss → run `python -m pipeline.run` → commit `data/shabla_events.db` + `docs/events.json` + `docs/source_stats.json` (guarded with `git diff --cached --quiet ||` so a no-change day doesn't fail the job).
- `pipeline/run.py` orchestrates: for each active source, isolated try/except around fetch → change-detect → relevance-filter → LLM-extract → dedup-and-store, logging a `source_runs` row regardless of outcome; after all sources, export both JSON files, then run `issues.py`'s check-and-file-issues pass.
- **Issue auto-filing** (`issues.py`, plain `requests` against the REST API): if a source's last N runs are all errors and no open issue exists, file one (title references the source), tracked in `source_issues`; if one exists, comment only on a changed error or after 7+ days; auto-close on the next success.
- Deploy: none needed beyond the commit — Pages (configured once via Settings → Pages → `main`/`/docs`) redeploys automatically when `docs/` changes land.

## Build order / milestones

1. **Scaffold** — repo, `.gitignore`, `requirements.txt`, empty package layout, and `AGENTS.md`. Verify: `python -m pipeline.run --help` runs.
2. **DB layer** — full DDL, idempotent. Verify: in-memory DB test confirms FTS5 MATCH works.
3. **`sources.yaml` + `manage.py` skeleton** — model, `list-sources`, `validate`, `add-source` (YAML-writing only). Verify: add the initial sources, `validate` passes.
4. **Fetchers** — `rss.py`, `html_generic.py`; wire `manage.py`'s dry-run fetch to them. Verify: dry-run against 2-3 real URLs prints sane samples.
5. **Change detection + storage** — hashing + fetch/store loop. Verify: running twice same day yields 0 new articles; deliberately break one source URL and confirm isolated error logging.
6. **Relevance filter** — bilingual geo/keyword lists, BM25+regex+geo gate. Verify: run against real Varna fetches *and* real Mangalia/Constanța fetches, manually calibrate `KEYWORD_THRESHOLD` and both-language geo lists — expect this to be the most iteration-heavy milestone.
7. **LLM extraction** — install `llama-cpp-python`, download the GGUF, author the grammar and prompt. Verify: run against fixture event/non-event articles in **both Bulgarian and Romanian**, plus at least one `adult_18+` fixture, confirm correct classification/categorization and field extraction, measure per-item latency.
8. **Dedup + events storage**. Verify: two fixtures describing the same event from different sources merge into one canonical event; dissimilar-dated events with similar titles do not merge.
9. **Export + static UI** — `events.json`/`source_stats.json`, `index.html`/`app.js`, `stats.html`/`stats.js`. Verify: render locally against fixture JSON, then enable Pages and confirm live URLs.
10. **Issue auto-filing**. Verify: seed 3 fake consecutive error rows for a test source, confirm an Issue is created; simulate a success and confirm auto-close.
11. **Actions workflow assembly** — write `daily.yml`, trigger repeatedly via `workflow_dispatch` to validate the full chain specifically inside the Actions environment (local success doesn't guarantee `llama-cpp-python` behaves identically on the runner). Verify: a real bot commit lands, both JSON exports update on the live Pages site, cron time is confirmed correct in Sofia local time.
12. **Calibration/soak** — run untouched for 1-2 weeks; review `source_stats.json` and any filed Issues; tune relevance thresholds, extend the geo list, adjust the LLM prompt based on observed false positives/negatives.

## Critical files

- `shabla-events/pipeline/run.py` — orchestrator
- `shabla-events/pipeline/db.py` — schema
- `shabla-events/pipeline/relevance.py` — cost-minimization filter
- `shabla-events/pipeline/llm/extractor.py` + `grammar.gbnf` — self-hosted extraction
- `shabla-events/sources.yaml` — source config
- `shabla-events/.github/workflows/daily.yml` — automation

## Verification

- Each milestone above has its own inline verification step.
- End-to-end: after Milestone 11, trigger the workflow manually via `workflow_dispatch`, confirm a commit lands from the bot identity, and confirm both `https://<user>.github.io/shabla-events/` (events) and its `/stats.html` (health dashboard) render real data.
- Ongoing: `manage.py show-stats` and the public stats page are the standing tools for judging whether a source is worth keeping; GitHub Issues are the standing tool for catching scraper breakage.

## Implementation notes (post-Milestone 6)

This section records deltas from the original design above, discovered
during actual implementation and live-data testing. The design above is
kept as the historical record of the original plan; this is what actually
shipped where it differs. See AGENTS.md for the authoritative current
architecture description.

- **Keyword scoring is not bm25().** The original design used SQLite
  FTS5's `bm25()` function for keyword relevance (an Elasticsearch-style
  analogy). Live testing showed bm25's IDF term degenerates toward zero on
  a small/growing corpus, making a fixed absolute threshold unstable (the
  same article's score drifts as more articles are added to the FTS index
  over time). Replaced with a plain weighted keyword hit-count in
  `pipeline/relevance.py` (title hits weighted 5x, body hits 1x,
  `KEYWORD_THRESHOLD = 3.0` as the starting calibration constant).
  `articles_fts`/`bm25` remain in the schema for potential future ad-hoc
  search, just not for this gate.
- **`assume_in_range` corrected for 5 sources**, based on live-data
  testing (a source passing only 1/12 real events was the tell):
  `shabla_sabitiya` (reclassified `structured-calendar` +
  `skip_keyword_filter: true` — it's a dedicated WordPress "event" post
  type, not generic news, so applying a keyword gate to it was wrong),
  `visit_varna_calendar`, `varna_culture`, `onevent_constanta`, and
  `zilesinopti_constanta` (all now `assume_in_range: true` — these are
  single-city event portals whose individual listings don't restate the
  city name, so the geo-mention gate was failing real events by design,
  not by miscalibration).
- **General lesson for future sources**: `assume_in_range: true` isn't
  just for "sources entirely about one municipality" as originally
  scoped — it also applies to any single-city event *portal* (calendar or
  dedicated event post type) where individual entries don't restate the
  city name. Check a new source's actual per-item text before assuming a
  `structured-calendar` type needs the geo gate.

## Implementation notes (post-Milestone 7)

- **Grammar-constrained decoding uses `LlamaGrammar.from_json_schema()`,
  not a hand-written `.gbnf` file.** The original design's GBNF grammar
  skeleton (in the original plan text above) enforced strict `YYYY-MM-DD`
  / `HH:MM` patterns and an exact key order at the grammar level. Multiple
  corrected variants of that hand-written grammar all passed
  `LlamaGrammar.from_file()`'s shallow parse check but caused a native
  **access-violation crash** deep in llama.cpp's sampler the moment they
  were actually used for generation -- a real fragility in this llama-cpp-
  python version's raw-GBNF path, not a one-off typo. Switched to building
  the grammar at runtime from a plain JSON Schema
  (`pipeline/llm/extractor.py`'s `JSON_SCHEMA`) via
  `LlamaGrammar.from_json_schema()`, which uses llama.cpp's own better-
  tested schema-to-grammar conversion and has not crashed. Tradeoff:
  `date`/`time` format is no longer grammar-enforced (JSON Schema
  `"pattern"` regex support was judged too uncertain to rely on given the
  crash risk already observed), so `extractor.py`'s `_normalize_date`/
  `_normalize_time` validate the model's output after parsing and blank
  out anything that doesn't match, rather than making malformed dates
  structurally impossible. Valid JSON with the exact key set is still
  guaranteed by the grammar either way.
- **Observed extraction latency**: 38-71s/item on CPU across the four
  live-tested fixtures (Bulgarian event, Bulgarian non-event, Romanian
  event, `adult_18+`) -- higher than the original 10-40s/item estimate,
  but still comfortably within the expected daily volume's time budget.
- **Live extraction test fixtures live in `tests/test_extractor_live.py`**,
  skipped automatically when the model weights aren't present locally, but
  will run for real in CI once Milestone 11's workflow downloads/caches
  the model -- giving an ongoing extraction-quality check on every run,
  not just a one-off Milestone 7 verification.
