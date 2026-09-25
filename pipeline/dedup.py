"""Cross-source near-duplicate event merging (Milestone 8).

Runs after an LLM-confirmed event, before it's written as a new canonical
row: normalize the title, look up candidate active events with a
compatible date, score by title similarity + location match, and either
merge into an existing canonical event or insert a new one. See AGENTS.md
for the algorithm summary.
"""
import re
import sqlite3
import unicodedata
from datetime import date, timedelta

from rapidfuzz import fuzz

from pipeline.geo import match_geo
from pipeline.llm.extractor import ExtractionResult

TITLE_SIMILARITY_THRESHOLD = 85
DATE_WINDOW_DAYS = 1


def normalize_title(title: str) -> str:
    """Lowercase, strip diacritics (handles Romanian ș/ț cedilla-vs-comma
    encoding inconsistencies), strip punctuation, collapse whitespace."""
    text = unicodedata.normalize("NFKD", title or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def dates_compatible(date1: str, date2: str, window_days: int = DATE_WINDOW_DAYS) -> bool:
    """Missing data is always compatible (don't let it block a merge); two
    real dates must be within window_days of each other -- this is what
    protects recurring annual events with similar titles but different
    years from being collapsed together."""
    if not date1 or not date2:
        return True
    try:
        d1 = date.fromisoformat(date1)
        d2 = date.fromisoformat(date2)
    except ValueError:
        return True
    return abs((d1 - d2).days) <= window_days


def same_location(loc1: str, loc2: str) -> bool:
    """Missing location data on either side is treated as compatible,
    consistent with the date-compatibility tolerance above."""
    l1 = (loc1 or "").strip().lower()
    l2 = (loc2 or "").strip().lower()
    if not l1 or not l2:
        return True
    if l1 == l2:
        return True
    tags1 = set(match_geo(loc1))
    tags2 = set(match_geo(loc2))
    return bool(tags1 and tags2 and (tags1 & tags2))


def _find_candidate_events(conn: sqlite3.Connection, event_date: str) -> list[sqlite3.Row]:
    if not event_date:
        return conn.execute("SELECT * FROM events WHERE status = 'active'").fetchall()
    try:
        d = date.fromisoformat(event_date)
    except ValueError:
        return conn.execute("SELECT * FROM events WHERE status = 'active'").fetchall()
    lo = (d - timedelta(days=DATE_WINDOW_DAYS)).isoformat()
    hi = (d + timedelta(days=DATE_WINDOW_DAYS)).isoformat()
    return conn.execute(
        "SELECT * FROM events WHERE status = 'active' AND "
        "(event_date IS NULL OR event_date = '' OR (event_date >= ? AND event_date <= ?))",
        (lo, hi),
    ).fetchall()


def find_matching_event(conn: sqlite3.Connection, title: str, event_date: str, location: str) -> sqlite3.Row | None:
    dedup_key = normalize_title(title)
    for candidate in _find_candidate_events(conn, event_date):
        if not dates_compatible(event_date, candidate["event_date"]):
            continue
        title_sim = fuzz.WRatio(dedup_key, candidate["dedup_key"] or "")
        if title_sim < TITLE_SIMILARITY_THRESHOLD:
            continue
        if not same_location(location, candidate["location"]):
            continue
        return candidate
    return None


def dedup_and_store(
    conn: sqlite3.Connection,
    extraction: ExtractionResult,
    article_id: int,
    source_id: str,
) -> int:
    """Merges into an existing canonical event or inserts a new one.
    Always links (event_id, article_id) via event_sources. Returns event_id."""
    dedup_key = normalize_title(extraction.title)
    match = find_matching_event(conn, extraction.title, extraction.date, extraction.location)

    if match is None:
        cur = conn.execute(
            "INSERT INTO events (title, event_date, event_time, location, category, description, dedup_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                extraction.title,
                extraction.date,
                extraction.time,
                extraction.location,
                extraction.category,
                extraction.description,
                dedup_key,
            ),
        )
        event_id = cur.lastrowid
    else:
        event_id = match["id"]
        updates: dict[str, str] = {}
        if not match["event_date"] and extraction.date:
            updates["event_date"] = extraction.date
        if not match["event_time"] and extraction.time:
            updates["event_time"] = extraction.time
        if not match["location"] and extraction.location:
            updates["location"] = extraction.location
        if len(extraction.description or "") > len(match["description"] or ""):
            updates["description"] = extraction.description
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE events SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
                (*updates.values(), event_id),
            )

    conn.execute(
        "INSERT OR IGNORE INTO event_sources (event_id, article_id, source_id, source_url) "
        "VALUES (?, ?, ?, ?)",
        (event_id, article_id, source_id, extraction.source_url),
    )
    return event_id
