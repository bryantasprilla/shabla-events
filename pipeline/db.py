"""SQLite schema management.

All statements are idempotent (CREATE ... IF NOT EXISTS) and re-run at the
start of every pipeline run -- this is the entire migration story at this
scale (see AGENTS.md).
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
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
    relevance_score REAL,
    geo_matched     TEXT,
    llm_raw_response TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_id, url)
);

CREATE INDEX IF NOT EXISTS idx_articles_source_status ON articles(source_id, status);

CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title, body, content='articles', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, body)
    VALUES('delete', old.id, old.title, old.body);
END;

CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, body)
    VALUES('delete', old.id, old.title, old.body);
    INSERT INTO articles_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    event_date      TEXT,
    event_time      TEXT,
    location        TEXT,
    category        TEXT,
    description     TEXT,
    dedup_key       TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
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

CREATE TABLE IF NOT EXISTS event_translations (
    event_id    INTEGER NOT NULL REFERENCES events(id),
    lang        TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (event_id, lang)
);

CREATE TABLE IF NOT EXISTS source_runs (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id                TEXT NOT NULL,
    run_at                   TEXT NOT NULL DEFAULT (datetime('now')),
    status                   TEXT NOT NULL,
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
    last_error_text     TEXT,
    resolved_at          TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite DB and ensure the schema exists.

    Pass ":memory:" for an ephemeral in-memory DB (used in tests).
    """
    if str(db_path) != ":memory:":
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        db_path = path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_article(
    conn: sqlite3.Connection,
    source_id: str,
    url: str,
    title: str,
    body: str,
    content_hash: str,
    published_at: str | None = None,
) -> tuple[int, bool]:
    """Insert a new article, or update an existing one at (source_id, url).

    Returns (article_id, is_new_or_changed). If the content_hash matches
    what's stored, only fetched_at is bumped and status/other fields are
    left untouched -- this is the change-detection gate (Milestone 5).
    """
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute(
        "SELECT id, content_hash FROM articles WHERE source_id = ? AND url = ?",
        (source_id, url),
    ).fetchone()

    if row is None:
        cur = conn.execute(
            "INSERT INTO articles (source_id, url, title, body, published_at, fetched_at, content_hash, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'new')",
            (source_id, url, title, body, published_at, now, content_hash),
        )
        return cur.lastrowid, True

    if row["content_hash"] == content_hash:
        conn.execute("UPDATE articles SET fetched_at = ? WHERE id = ?", (now, row["id"]))
        return row["id"], False

    conn.execute(
        "UPDATE articles SET title = ?, body = ?, published_at = ?, fetched_at = ?, "
        "content_hash = ?, status = 'new', updated_at = ? WHERE id = ?",
        (title, body, published_at, now, content_hash, now, row["id"]),
    )
    return row["id"], True


def record_source_run(
    conn: sqlite3.Connection,
    source_id: str,
    status: str,
    http_status: int | None = None,
    error_message: str | None = None,
    articles_fetched: int = 0,
    articles_new_or_changed: int = 0,
    articles_passed_filter: int = 0,
    events_confirmed: int = 0,
    duration_ms: int | None = None,
) -> None:
    conn.execute(
        "INSERT INTO source_runs (source_id, status, http_status, error_message, "
        "articles_fetched, articles_new_or_changed, articles_passed_filter, "
        "events_confirmed, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source_id,
            status,
            http_status,
            error_message,
            articles_fetched,
            articles_new_or_changed,
            articles_passed_filter,
            events_confirmed,
            duration_ms,
        ),
    )
