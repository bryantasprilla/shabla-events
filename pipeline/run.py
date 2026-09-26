"""Daily pipeline orchestrator entrypoint.

Per source: fetch -> change-detect -> relevance-filter -> LLM-extract -> dedup-and-store.
Each source's steps are isolated so one failure never blocks the others (see AGENTS.md).

After all sources: export the public JSON files, then file/update/close
GitHub Issues for repeatedly-failing sources.
"""
import argparse
import json
import time
from dataclasses import dataclass

from pipeline.config import Settings, Source, load_config
from pipeline.db import connect, record_source_run, upsert_article
from pipeline.dedup import dedup_and_store
from pipeline.export import export_events_json, export_source_stats_json
from pipeline.fetchers.html_generic import fetch_html
from pipeline.fetchers.rss import fetch_rss
from pipeline.hashing import content_hash
from pipeline.issues import check_and_file_issues
from pipeline.llm.extractor import Extractor
from pipeline.relevance import evaluate_relevance


@dataclass
class LlmBudget:
    """Caps LLM extractions per run. Extraction is by far the slowest step
    (~40-70s/article on CPU), and calendar sources skip the keyword gate, so
    a first run against a big backlog could otherwise run for hours. Articles
    beyond the cap stay status='sent_to_llm' and are picked up on the next
    run -- nothing is dropped, just deferred."""

    remaining: int

    def take(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


def fetch_source(source: Source, settings: Settings) -> list:
    if source.type == "rss":
        return fetch_rss(source.url, timeout_s=settings.request_timeout_s, user_agent=settings.user_agent)
    return fetch_html(
        source.url,
        source.selectors or {},
        timeout_s=settings.request_timeout_s,
        user_agent=settings.user_agent,
    )


def apply_relevance_filter(conn, source: Source) -> int:
    """Scores and gates every 'new' article for this source. Returns the
    count that passed (now status='sent_to_llm', ready for extraction)."""
    rows = conn.execute(
        "SELECT id, title, body FROM articles WHERE source_id = ? AND status = 'new'",
        (source.id,),
    ).fetchall()
    passed = 0
    for row in rows:
        score, geo_matched, ok = evaluate_relevance(row["title"], row["body"], source)
        conn.execute(
            "UPDATE articles SET relevance_score = ?, geo_matched = ?, status = ? WHERE id = ?",
            (score, json.dumps(geo_matched), "sent_to_llm" if ok else "filtered_out", row["id"]),
        )
        if ok:
            passed += 1
    return passed


def run_llm_extraction(conn, source: Source, extractor: Extractor, budget: LlmBudget | None = None) -> int:
    """Extracts + dedups 'sent_to_llm' articles for this source, up to the
    shared per-run budget. Returns the count confirmed as real events."""
    rows = conn.execute(
        "SELECT id, url, title, body FROM articles WHERE source_id = ? AND status = 'sent_to_llm' ORDER BY id",
        (source.id,),
    ).fetchall()
    confirmed = 0
    for row in rows:
        if budget is not None and not budget.take():
            print(f"[{source.id}] LLM budget exhausted; remaining articles deferred to the next run")
            break
        try:
            result = extractor.extract(source.name, row["url"], row["title"], row["body"])
        except Exception as e:
            # One bad article (e.g. model output truncated at max_tokens ->
            # invalid JSON) must not abort the whole source or lose its
            # progress -- mark just this article as errored and move on.
            print(f"[{source.id}] extraction failed for {row['url']}: {e}")
            conn.execute(
                "UPDATE articles SET llm_raw_response = ?, status = 'error' WHERE id = ?",
                (f"ERROR: {e}", row["id"]),
            )
            continue
        conn.execute(
            "UPDATE articles SET llm_raw_response = ?, status = ? WHERE id = ?",
            (result.raw_response, "event_confirmed" if result.is_event else "not_event", row["id"]),
        )
        if result.is_event:
            dedup_and_store(conn, result, article_id=row["id"], source_id=source.id)
            confirmed += 1
    return confirmed


def translate_pending_events(conn, extractor: Extractor, limit: int) -> int:
    """Translates active events that have no translations yet into en/bg/ro
    (soonest-dated first), caching them in event_translations. Only confirmed
    events are translated -- a few dozen, not every scraped article. A failure
    on one event is logged and skipped (it's retried next run). Returns the
    number of events translated."""
    rows = conn.execute(
        "SELECT id, title, description FROM events e WHERE status = 'active' "
        "AND (event_date IS NULL OR event_date = '' OR event_date >= date('now')) "
        "AND NOT EXISTS (SELECT 1 FROM event_translations t WHERE t.event_id = e.id) "
        "ORDER BY (event_date IS NULL OR event_date = ''), event_date, id LIMIT ?",
        (limit,),
    ).fetchall()
    done = 0
    for row in rows:
        try:
            translations = extractor.translate(row["title"], row["description"] or "")
        except Exception as e:
            print(f"translation failed for event {row['id']}: {e}")
            continue
        for lang, tr in translations.items():
            conn.execute(
                "INSERT OR REPLACE INTO event_translations (event_id, lang, title, description) VALUES (?, ?, ?, ?)",
                (row["id"], lang, tr["title"] or row["title"], tr["description"]),
            )
        conn.commit()
        done += 1
    return done


def run_source(
    conn, source: Source, settings: Settings, extractor: Extractor, budget: LlmBudget | None = None
) -> None:
    start = time.monotonic()
    try:
        items = fetch_source(source, settings)
        new_or_changed = 0
        for item in items:
            h = content_hash(item.title, item.body)
            _, changed = upsert_article(conn, source.id, item.url, item.title, item.body, h, item.published_at)
            if changed:
                new_or_changed += 1
        passed_filter = apply_relevance_filter(conn, source)
        events_confirmed = run_llm_extraction(conn, source, extractor, budget)
        duration_ms = int((time.monotonic() - start) * 1000)
        record_source_run(
            conn,
            source.id,
            status="success",
            articles_fetched=len(items),
            articles_new_or_changed=new_or_changed,
            articles_passed_filter=passed_filter,
            events_confirmed=events_confirmed,
            duration_ms=duration_ms,
        )
        conn.commit()
        print(
            f"[{source.id}] ok: {len(items)} fetched, {new_or_changed} new/changed, "
            f"{passed_filter} passed filter, {events_confirmed} events confirmed"
        )
    except Exception as e:
        conn.rollback()
        duration_ms = int((time.monotonic() - start) * 1000)
        record_source_run(conn, source.id, status="error", error_message=str(e), duration_ms=duration_ms)
        conn.commit()
        print(f"[{source.id}] ERROR: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Shabla Events pipeline orchestrator")
    parser.add_argument("--db", default="data/shabla_events.db")
    parser.add_argument("--sources", default="sources.yaml")
    parser.add_argument("--model", default="models/qwen2.5-7b-instruct-q4_k_m.gguf")
    parser.add_argument("--events-json", default="docs/events.json")
    parser.add_argument("--stats-json", default="docs/source_stats.json")
    parser.add_argument("--max-llm-per-run", type=int, default=60)
    parser.add_argument("--max-translate-per-run", type=int, default=40)
    args = parser.parse_args()

    config = load_config(args.sources)
    conn = connect(args.db)
    extractor = Extractor(args.model)
    budget = LlmBudget(args.max_llm_per_run)

    for source in config.sources:
        if not source.active:
            continue
        run_source(conn, source, config.settings, extractor, budget)

    queued = conn.execute("SELECT COUNT(*) FROM articles WHERE status = 'sent_to_llm'").fetchone()[0]
    if queued:
        print(f"{queued} article(s) still queued for LLM extraction on the next run")

    translated = translate_pending_events(conn, extractor, args.max_translate_per_run)
    print(f"Translated {translated} event(s) into en/bg/ro")

    events_written = export_events_json(conn, config, args.events_json)
    sources_written = export_source_stats_json(conn, config, args.stats_json)
    print(f"Exported {events_written} events to {args.events_json}, {sources_written} source stats to {args.stats_json}")

    try:
        check_and_file_issues(conn, config)
    except RuntimeError as e:
        # GITHUB_TOKEN/GITHUB_REPOSITORY are only set inside a GitHub Actions
        # job -- don't fail a local dev run just because issue-filing can't run.
        print(f"Skipping issue auto-filing: {e}")


if __name__ == "__main__":
    main()
