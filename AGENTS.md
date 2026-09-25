# AGENTS.md — shabla-events

## What this project is

An automated pipeline that scrapes local/regional news and event-calendar
sites near Shabla, Bulgaria (and, across the border, southeastern Romania —
Constanța and the coast south of it), extracts real-world local events using
a self-hosted LLM, and publishes them as a public static webpage. Built to
run at $0 recurring cost.

## Non-negotiable constraints (do not "improve" these away)

- **Zero recurring cost.** No paid APIs, no paid hosting, no hosted DB.
  Everything runs on GitHub Actions free minutes + GitHub Pages + a
  self-hosted open-source LLM. If a change would introduce a bill, it's
  out of scope unless the user explicitly asks for it.
- **Self-hosted LLM only** — Qwen2.5-7B-Instruct (GGUF, Q4_K_M) via
  `llama-cpp-python`, run inside the GitHub Actions runner itself. Do not
  swap in a hosted API (Anthropic/OpenAI/etc.) as a "simpler" alternative;
  cost-minimization was an explicit, deliberate requirement, not a default.
- **One unified extraction pipeline.** Every source — including
  already-structured event-calendar sites (visit.varna.bg, varnaculture.bg,
  onevent.ro, zilesinopti.ro) — goes through the same
  fetch → change-detect → relevance-filter → LLM-extract path ending in one
  consistent schema. Do not special-case a "direct parse" shortcut for
  structured sources; this was explicitly decided against so the LLM stays
  the single point of schema normalization.
- **`sources.yaml` + `manage.py` is the admin interface.** No hosted admin
  UI, no auth system. Adding/removing sources happens via the CLI + git
  push. Don't build a web form for this.
- **Bilingual (Bulgarian + Romanian).** Keyword lists, geo place-lists, and
  the LLM prompt must handle both languages. Don't assume Bulgarian-only.

## Architecture (pipeline order, per source, isolated per source)

1. **Fetch** (`pipeline/fetchers/`) — RSS (`rss.py`) or CSS-selector HTML
   scrape (`html_generic.py`, used for both `html-article-list` and
   `structured-calendar` source types — same mechanics, different selector
   intent).
2. **Change detection** (`pipeline/hashing.py`) — hash title+body; skip
   anything whose hash already exists in `articles`.
3. **Relevance filter** (`pipeline/relevance.py`) — cheap pre-screen before
   the expensive LLM step, modeled on adverse-media relevancy scoring: a
   bilingual weighted keyword hit-count (title hits weighted above body
   hits) plus a date/time regex bonus, and a geo place-name gate
   (`pipeline/geo.py`). Sources flagged `assume_in_range: true` skip the
   geo gate — use this both for sources that are inherently and entirely
   about one place (a single municipality's own site) *and* for
   single-city event portals whose per-event listings don't restate the
   city name (visit.varna.bg, onevent.ro/constanta) — don't assume a
   "calendar" type automatically needs the geo gate; check whether its
   content actually mentions place names or just relies on being hosted
   under that city's own domain. Sources flagged `skip_keyword_filter:
   true` (structured calendars, or a dedicated "event" post type like
   shabla.bg/events/) skip the keyword gate but still typically need
   `assume_in_range` too, since the content is already known to be an
   event without restating where. NOTE: an earlier version of this filter
   used SQLite FTS5's bm25() ranking function, matching the plan's
   original design (an Elasticsearch-relevancy analogy). Live testing
   showed bm25's IDF term degenerates toward zero on a small/growing
   corpus, so a fixed threshold isn't stable over time -- replaced with
   the plain weighted hit-count above. `articles_fts` stays in the schema
   for potential future ad-hoc search, just not for this gate.
4. **LLM extraction** (`pipeline/llm/`) — Qwen2.5-7B-Instruct via
   `llama-cpp-python`, output forced into a strict schema by GBNF grammar
   (`grammar.gbnf`): `{is_event, title, date, time, location, category,
   description, source_url}`. `category` enum:
   `concert|festival|exhibition|municipal|sports|theater|adult_18+|other`.
   `source_url` is always overwritten with the known article URL after
   parsing — never trust the model to reproduce it faithfully. On Windows,
   `pip install llama-cpp-python` can hit a MAX_PATH build failure (the
   source distribution vendors llama.cpp's full source tree); use
   `--prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`
   for local dev instead (see requirements.txt comment). The model weights
   themselves (`models/qwen2.5-7b-instruct-q4_k_m.gguf`, ~4.68GB, from
   `bartowski/Qwen2.5-7B-Instruct-GGUF` on Hugging Face — Qwen's own GGUF
   upload splits Q4_K_M across two shard files, bartowski's re-upload is a
   single file) are gitignored and not part of `pip install`; they're
   fetched separately (curl in CI, manual download for local dev).
5. **Dedup** (`pipeline/dedup.py`) — fuzzy title match (rapidfuzz,
   threshold ~85) + location/geo-tag match + date compatibility (±1 day,
   never merge across a clear date mismatch) merges the same event
   reported by multiple sources into one canonical `events` row, linked
   via `event_sources`.
6. **Export** (`pipeline/export.py`) — `docs/events.json` (public events
   page) and `docs/source_stats.json` (public stats/health dashboard).

Errors during any source's fetch/filter/extract are caught, logged to
`source_runs`, and never abort the run for other sources. A source failing
N consecutive runs (default 3, overridable per-source in `sources.yaml`)
auto-files a GitHub Issue (`pipeline/issues.py`); it auto-closes on the
next success.

## Key files

- `pipeline/run.py` — orchestrator, the daily job's entrypoint
- `pipeline/db.py` — SQLite schema (idempotent `CREATE ... IF NOT EXISTS`;
  this is the entire migration story at this scale)
- `pipeline/relevance.py`, `pipeline/geo.py` — the cost-minimization filter
- `pipeline/llm/extractor.py`, `pipeline/llm/grammar.gbnf` — self-hosted
  extraction
- `sources.yaml` — source config (source of truth)
- `manage.py` — admin CLI (`add-source`, `remove-source`, `validate`,
  `test-source`, `show-stats`, `activate-source`/`deactivate-source`)
- `.github/workflows/daily.yml` — the only automation; commits
  `data/shabla_events.db` + `docs/*.json` back to `main` each run, which
  is also the GitHub Pages deploy (served from `/docs`)

## Conventions

- New sources are added via `manage.py add-source`, never by hand-editing
  `sources.yaml` directly for anything beyond trivial fixes — the CLI's
  dry-run test-fetch is what prevents a bad selector from being committed
  silently.
- Every new source needs `geo_tags` from the canonical list in `geo.py`;
  extend that list (both languages) rather than inventing ad-hoc tags.
- Structured-calendar sources always get `skip_keyword_filter: true`;
  `assume_in_range` is only for sources that are inherently and entirely
  about the covered area (e.g. a single municipality's own site) — regional
  city-wide sources (Varna, Constanța) are never `assume_in_range`.
- Don't add retry/repair logic around LLM JSON output — the GBNF grammar
  makes malformed JSON structurally impossible; if output is wrong, it's a
  semantic/calibration problem (fix the prompt or keyword/geo lists), not a
  parsing problem.

## Status / next steps

See the build-order milestones in `PLAN.md`. Known calibration risks going
in: relevance-filter thresholds and the geo place-list are expected to need
tuning after the initial soak period (Milestone 12), and
`llama-cpp-python`'s behavior on the actual `ubuntu-latest` Actions runner
should be verified early (Milestone 11) rather than assumed from local
testing.
