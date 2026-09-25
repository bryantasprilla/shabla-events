"""Auto-files/comments-on/closes GitHub Issues for repeatedly-failing
sources (Milestone 10). This is the error-resolution inbox -- no separate
notification system needed (see AGENTS.md).

Uses the GitHub REST API directly via `requests` (a handful of simple
calls doesn't need a PyGithub dependency). Requires GITHUB_TOKEN and
GITHUB_REPOSITORY in the environment -- both provided automatically by a
GitHub Actions job.
"""
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import requests

from pipeline.config import Config, Source

GITHUB_API = "https://api.github.com"
COMMENT_COOLDOWN_DAYS = 7


def _repo_slug() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY environment variable is not set")
    return repo


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN environment variable is not set")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _recent_runs(conn: sqlite3.Connection, source_id: str, n: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM source_runs WHERE source_id = ? ORDER BY run_at DESC LIMIT ?",
        (source_id, n),
    ).fetchall()


def _get_source_issue(conn: sqlite3.Connection, source_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM source_issues WHERE source_id = ?", (source_id,)).fetchone()


def _upsert_source_issue(conn: sqlite3.Connection, source_id: str, **fields) -> None:
    existing = _get_source_issue(conn, source_id)
    if existing is None:
        cols = ", ".join(["source_id"] + list(fields.keys()))
        placeholders = ", ".join(["?"] * (1 + len(fields)))
        conn.execute(
            f"INSERT INTO source_issues ({cols}) VALUES ({placeholders})",
            (source_id, *fields.values()),
        )
    else:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE source_issues SET {set_clause} WHERE source_id = ?", (*fields.values(), source_id))
    conn.commit()


def _create_issue(source: Source, threshold: int, error_message: str) -> int:
    resp = requests.post(
        f"{GITHUB_API}/repos/{_repo_slug()}/issues",
        headers=_headers(),
        json={
            "title": f"[shabla-events] Source failing: {source.name} ({source.id})",
            "body": (
                f"Source `{source.id}` ({source.url}) has failed its last {threshold} run(s).\n\n"
                f"Latest error:\n```\n{error_message}\n```\n\n"
                f"First response: `python manage.py test-source {source.id}` to see the failure "
                f"directly, or `python manage.py deactivate-source --id {source.id}` to pause it "
                f"while investigating."
            ),
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["number"]


def _comment_on_issue(issue_number: int, error_message: str) -> None:
    resp = requests.post(
        f"{GITHUB_API}/repos/{_repo_slug()}/issues/{issue_number}/comments",
        headers=_headers(),
        json={"body": f"Still failing:\n```\n{error_message}\n```"},
        timeout=20,
    )
    resp.raise_for_status()


def _close_issue(issue_number: int) -> None:
    resp = requests.patch(
        f"{GITHUB_API}/repos/{_repo_slug()}/issues/{issue_number}",
        headers=_headers(),
        json={"state": "closed"},
        timeout=20,
    )
    resp.raise_for_status()


def _parse_ts(value: str) -> datetime:
    """Parses a stored timestamp, treating a naive value as UTC. Needed
    because SQLite's own `datetime('now')` default (used elsewhere in the
    schema) produces a naive string, while this module's own writes use
    timezone-aware `now.isoformat()` -- both must compare safely."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_issue_open(existing) -> bool:
    return existing is not None and existing["github_issue_number"] is not None and existing["resolved_at"] is None


def check_and_file_issues(conn: sqlite3.Connection, config: Config) -> None:
    now = datetime.now(timezone.utc)

    for source in config.sources:
        threshold = source.consecutive_failure_threshold or config.settings.consecutive_failure_threshold
        recent = _recent_runs(conn, source.id, threshold)
        all_failed = len(recent) == threshold and all(r["status"] == "error" for r in recent)
        existing = _get_source_issue(conn, source.id)
        last_error = recent[0]["error_message"] if recent else None

        if all_failed:
            if not _is_issue_open(existing):
                issue_number = _create_issue(source, threshold, last_error or "unknown error")
                _upsert_source_issue(
                    conn, source.id,
                    github_issue_number=issue_number,
                    opened_at=now.isoformat(),
                    last_commented_at=now.isoformat(),
                    last_error_text=last_error,
                    resolved_at=None,
                )
                continue

            error_changed = existing["last_error_text"] != last_error
            cooldown_elapsed = True
            if existing["last_commented_at"]:
                cooldown_elapsed = (now - _parse_ts(existing["last_commented_at"])) >= timedelta(
                    days=COMMENT_COOLDOWN_DAYS
                )
            if error_changed or cooldown_elapsed:
                _comment_on_issue(existing["github_issue_number"], last_error or "unknown error")
                _upsert_source_issue(
                    conn, source.id, last_commented_at=now.isoformat(), last_error_text=last_error
                )
        elif recent and recent[0]["status"] == "success" and _is_issue_open(existing):
            _close_issue(existing["github_issue_number"])
            _upsert_source_issue(conn, source.id, resolved_at=now.isoformat())
