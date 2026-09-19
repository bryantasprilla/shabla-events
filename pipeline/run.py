"""Daily pipeline orchestrator entrypoint.

Per source: fetch -> change-detect -> relevance-filter -> LLM-extract -> dedup-and-store.
Each source's steps are isolated so one failure never blocks the others (see AGENTS.md).

Currently implements fetch + change-detection + per-source error isolation
(Milestones 4-5). Relevance filtering, LLM extraction, dedup, and export
land in Milestones 6-9.
"""
import argparse
import time

from pipeline.config import Settings, Source, load_config
from pipeline.db import connect, record_source_run, upsert_article
from pipeline.fetchers.html_generic import fetch_html
from pipeline.fetchers.rss import fetch_rss
from pipeline.hashing import content_hash


def fetch_source(source: Source, settings: Settings) -> list:
    if source.type == "rss":
        return fetch_rss(source.url, timeout_s=settings.request_timeout_s, user_agent=settings.user_agent)
    return fetch_html(
        source.url,
        source.selectors or {},
        timeout_s=settings.request_timeout_s,
        user_agent=settings.user_agent,
    )


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
        duration_ms = int((time.monotonic() - start) * 1000)
        record_source_run(
            conn,
            source.id,
            status="success",
            articles_fetched=len(items),
            articles_new_or_changed=new_or_changed,
            duration_ms=duration_ms,
        )
        conn.commit()
        print(f"[{source.id}] ok: {len(items)} fetched, {new_or_changed} new/changed")
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

    # TODO Milestone 6: relevance filter articles with status='new'
    # TODO Milestone 7: LLM extraction for articles that pass the filter
    # TODO Milestone 8: cross-source dedup into events/event_sources
    # TODO Milestone 9: export docs/events.json, docs/source_stats.json


if __name__ == "__main__":
    main()
