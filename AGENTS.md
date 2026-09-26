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
   `llama-cpp-python`, output forced into a strict schema via
   `LlamaGrammar.from_json_schema(JSON_SCHEMA)` (the schema lives in
   `extractor.py`, not a static `.gbnf` file -- an earlier hand-written
   GBNF grammar caused a native access-violation crash deep in the sampler
   despite passing a shallow parse check; see extractor.py's module
   docstring for the full story): `{is_event, title, date, time, location, category, description,
   source_url}`. `category` enum:
   `concert|festival|exhibition|municipal|sports|theater|adult_18+|other`.
   `source_url` is always overwritten with the known article URL after
   parsing — never trust the model to reproduce it faithfully. Live-tested
   against Bulgarian event/non-event, Romanian event, and `adult_18+`
   fixtures -- all four classified and extracted correctly; observed
   latency was 38-71s/item on CPU (higher than the original 10-40s
   estimate, still fine at expected daily volume). On Windows,
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
- `pipeline/llm/extractor.py` (includes `JSON_SCHEMA`), `pipeline/llm/prompt.py`
  — self-hosted extraction
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
- Structured-calendar sources always get `skip_keyword_filter: true`.
  `assume_in_range` applies to any source whose *individual entries* won't
  restate an in-range place name — this includes a single municipality's
  own site, but also single-city event portals (visit.varna.bg,
  onevent.ro/constanta) where every listing is inherently in that city
  without saying so per-item. It's only false for genuinely broad regional
  sources (a general news outlet covering a whole province) where the geo
  gate has to look for an actual place-name mention to know an article is
  in range. Check a new source's real per-item text before assuming which
  bucket it's in — see PLAN.md's "Implementation notes" for the sources
  this was corrected on after live-data testing.
- Don't add retry/repair logic around LLM JSON output — grammar-constrained
  decoding makes malformed JSON structurally impossible *as long as the
  model finishes*: hitting `max_tokens` truncates mid-string (seen on long
  Cyrillic descriptions), which the extractor now detects via
  `finish_reason == "length"`, and `run_llm_extraction` isolates any
  per-article failure (status='error') instead of aborting the source; if output is wrong, it's a
  semantic/calibration problem (fix the prompt or keyword/geo lists), not a
  parsing problem.

## Fetcher notes (learned calibrating real sites)

- `selectors.base_url` overrides what relative hrefs resolve against, for
  sites (balchik.bg) that write links like `bg/novini/x` meant relative to
  the site root, not the current page.
- If `list_item` matches `<a>` tags themselves (portal-silistra.eu,
  onevent.ro), the node's own `href` is used -- no nested link selector needed.
- `html_generic.py` overrides requests' ISO-8859-1 fallback with the
  detected encoding (moreto.net is windows-1251 with no charset header).
- Beware a `list_item` of plain `article`: some themes wrap the whole page in
  an `<article>`, so a loose selector can "work" by grabbing the same first
  headline repeatedly (silistra_news did this unnoticed). Always eyeball
  `manage.py test-source` output for duplicate titles.
- Some sites can't be scraped: mangalia.tv serves a reCAPTCHA bot check
  (source kept but `active: false`); dobrichonline.com 403s GitHub's IP
  ranges but not residential ones. Don't try to defeat bot protection.
- `--max-llm-per-run` (default 60) caps LLM extractions per run; overflow
  stays `status='sent_to_llm'` and is processed on later runs, so a big
  first-run backlog spreads over several days instead of hitting the job limit.

## Status / next steps

See the build-order milestones in `PLAN.md`. Known calibration risks going
in: relevance-filter thresholds and the geo place-list are expected to need
tuning after the initial soak period (Milestone 12), and
`llama-cpp-python`'s behavior on the actual `ubuntu-latest` Actions runner
should be verified early (Milestone 11) rather than assumed from local
testing.
