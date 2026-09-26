"""Exports docs/events.json (public events page) and docs/source_stats.json
(public stats/health dashboard) -- Milestone 9.
"""
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pipeline.config import Config

STATS_WINDOW_DAYS = 30


def _mark_past_events(conn: sqlite3.Connection, today: date) -> None:
    """Dated events before today move from active -> past so they drop out
    of the public export without being deleted."""
    conn.execute(
        "UPDATE events SET status = 'past', updated_at = datetime('now') "
        "WHERE status = 'active' AND event_date != '' AND event_date < ?",
        (today.isoformat(),),
    )
    conn.commit()


def export_events_json(
    conn: sqlite3.Connection,
    config: Config,
    output_path: str | Path,
    today: date | None = None,
) -> int:
    """Writes the public events export. Returns the number of events written."""
    today = today or date.today()
    _mark_past_events(conn, today)

    source_names = {s.id: s.name for s in config.sources}

    events = conn.execute(
        "SELECT * FROM events WHERE status = 'active' "
        "ORDER BY (event_date = '') ASC, event_date ASC, event_time ASC"
    ).fetchall()

    result = []
    for e in events:
        sources = conn.execute(
            "SELECT source_id, source_url FROM event_sources WHERE event_id = ?",
            (e["id"],),
        ).fetchall()
        translations = {
            t["lang"]: {"title": t["title"], "description": t["description"]}
            for t in conn.execute(
                "SELECT lang, title, description FROM event_translations WHERE event_id = ?",
                (e["id"],),
            ).fetchall()
        }
        result.append(
            {
                "translations": translations,
                "id": e["id"],
                "title": e["title"],
                "date": e["event_date"] or "",
                "time": e["event_time"] or "",
                "location": e["location"] or "",
                "category": e["category"] or "other",
                "description": e["description"] or "",
                "sources": [
                    {
                        "source_id": s["source_id"],
                        "source_name": source_names.get(s["source_id"], s["source_id"]),
                        "url": s["source_url"],
                    }
                    for s in sources
                ],
            }
        )

    _write_json(output_path, {"generated_at": _now_iso(), "events": result})
    return len(result)


def export_source_stats_json(
    conn: sqlite3.Connection,
    config: Config,
    output_path: str | Path,
    days: int = STATS_WINDOW_DAYS,
) -> int:
    """Writes the public stats/health export. Returns the number of sources written."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    stats = []
    for source in config.sources:
        runs = conn.execute(
            "SELECT * FROM source_runs WHERE source_id = ? AND run_at >= ? ORDER BY run_at DESC",
            (source.id, cutoff),
        ).fetchall()

        total_fetched = sum(r["articles_fetched"] for r in runs)
        total_new = sum(r["articles_new_or_changed"] for r in runs)
        total_passed = sum(r["articles_passed_filter"] for r in runs)
        total_confirmed = sum(r["events_confirmed"] for r in runs)
        last_run = runs[0] if runs else None
        last_success = next((r for r in runs if r["status"] == "success"), None)
        last_error_row = next((r for r in runs if r["status"] == "error"), None)

        stats.append(
            {
                "source_id": source.id,
                "source_name": source.name,
                "tier": source.tier,
                "active": source.active,
                "runs_in_window": len(runs),
                "articles_fetched": total_fetched,
                "articles_new_or_changed": total_new,
                "articles_passed_filter": total_passed,
                "events_confirmed": total_confirmed,
                "pass_rate": round(total_passed / total_new, 3) if total_new else None,
                "confirm_rate": round(total_confirmed / total_passed, 3) if total_passed else None,
                "last_run_at": last_run["run_at"] if last_run else None,
                "last_run_status": last_run["status"] if last_run else None,
                "last_success_at": last_success["run_at"] if last_success else None,
                "last_error": last_error_row["error_message"] if last_error_row else None,
            }
        )

    _write_json(
        output_path,
        {"generated_at": _now_iso(), "window_days": days, "sources": stats},
    )
    return len(stats)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(output_path: str | Path, data: dict) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
