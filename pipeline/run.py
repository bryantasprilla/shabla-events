"""Daily pipeline orchestrator entrypoint.

Per source: fetch -> change-detect -> relevance-filter -> LLM-extract -> dedup-and-store.
Each source's steps are isolated so one failure never blocks the others (see AGENTS.md).

Currently implements fetch + change-detection + relevance filtering +
per-source error isolation (Milestones 4-6). LLM extraction, dedup, and
export land in Milestones 7-9.
"""
import argparse
import json
import time

from pipeline.config import Settings, Source, load_config
from pipeline.db import connect, record_source_run, upsert_article
from pipeline.fetchers.html_generic import fetch_html
from pipeline.fetchers.rss import fetch_rss
from pipeline.hashing import content_hash
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
    count that passed (now status='sent_to_llm', ready for Milestone 7)."""
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


def run_source(conn, source: Source, settings: Settings) -> None:
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
        duration_ms = int((time.monotonic() - start) * 1000)
        record_source_run(
            conn,
            source.id,
            status="success",
            articles_fetched=len(items),
            articles_new_or_changed=new_or_changed,
            articles_passed_filter=passed_filter,
            duration_ms=duration_ms,
        )
        conn.commit()
        print(f"[{source.id}] ok: {len(items)} fetched, {new_or_changed} new/changed, {passed_filter} passed filter")
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
    parser.add_argument("--grammar", default="pipeline/llm/grammar.gbnf")
    args = parser.parse_args()

    config = load_config(args.sources)
    conn = connect(args.db)

    for source in config.sources:
        if not source.active:
            continue
        run_source(conn, source, config.settings)

    # TODO Milestone 7: LLM extraction for articles with status='sent_to_llm'
    # TODO Milestone 8: cross-source dedup into events/event_sources
    # TODO Milestone 9: export docs/events.json, docs/source_stats.json


if __name__ == "__main__":
    main()
