"""Daily pipeline orchestrator entrypoint.

Per source: fetch -> change-detect -> relevance-filter -> LLM-extract -> dedup-and-store.
Each source's steps are isolated so one failure never blocks the others (see AGENTS.md).

Implements the full chain through Milestone 8. Export (Milestone 9) and
GitHub Issue auto-filing (Milestone 10) are still TODO.
"""
import argparse
import json
import time

from pipeline.config import Settings, Source, load_config
from pipeline.db import connect, record_source_run, upsert_article
from pipeline.dedup import dedup_and_store
from pipeline.fetchers.html_generic import fetch_html
from pipeline.fetchers.rss import fetch_rss
from pipeline.hashing import content_hash
from pipeline.llm.extractor import Extractor
from pipeline.relevance import evaluate_relevance


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


def run_llm_extraction(conn, source: Source, extractor: Extractor) -> int:
    """Extracts + dedups every 'sent_to_llm' article for this source.
    Returns the count confirmed as real events."""
    rows = conn.execute(
        "SELECT id, url, title, body FROM articles WHERE source_id = ? AND status = 'sent_to_llm'",
        (source.id,),
    ).fetchall()
    confirmed = 0
    for row in rows:
        result = extractor.extract(source.name, row["url"], row["title"], row["body"])
        conn.execute(
            "UPDATE articles SET llm_raw_response = ?, status = ? WHERE id = ?",
            (result.raw_response, "event_confirmed" if result.is_event else "not_event", row["id"]),
        )
        if result.is_event:
            dedup_and_store(conn, result, article_id=row["id"], source_id=source.id)
            confirmed += 1
    return confirmed


def run_source(conn, source: Source, settings: Settings, extractor: Extractor) -> None:
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
        events_confirmed = run_llm_extraction(conn, source, extractor)
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
    args = parser.parse_args()

    config = load_config(args.sources)
    conn = connect(args.db)
    extractor = Extractor(args.model)

    for source in config.sources:
        if not source.active:
            continue
        run_source(conn, source, config.settings, extractor)

    # TODO Milestone 9: export docs/events.json, docs/source_stats.json
    # TODO Milestone 10: GitHub Issue auto-filing for repeatedly-failing sources


if __name__ == "__main__":
    main()
