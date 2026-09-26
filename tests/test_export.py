import json
from datetime import date
from pathlib import Path

from pipeline.config import Config, Settings, Source
from pipeline.db import connect
from pipeline.export import export_events_json, export_source_stats_json

SOURCE = Source(id="s1", name="Source One", tier=1, type="rss", url="https://example.com")
CONFIG = Config(settings=Settings(), sources=[SOURCE])


def _insert_event(conn, title, event_date, source_id="s1", article_id=1):
    cur = conn.execute(
        "INSERT INTO events (title, event_date, event_time, location, category, description, dedup_key) "
        "VALUES (?, ?, '', 'Shabla', 'concert', 'desc', ?)",
        (title, event_date, title.lower()),
    )
    event_id = cur.lastrowid
    conn.execute(
        "INSERT INTO event_sources (event_id, article_id, source_id, source_url) VALUES (?, ?, ?, ?)",
        (event_id, article_id, source_id, "https://example.com/a"),
    )
    conn.commit()
    return event_id


def test_export_events_json_excludes_past_events(tmp_path: Path):
    conn = connect(":memory:")
    _insert_event(conn, "Future Concert", "2026-12-31")
    _insert_event(conn, "Past Concert", "2020-01-01", article_id=2)
    _insert_event(conn, "Undated Exhibition", "", article_id=3)

    out = tmp_path / "events.json"
    count = export_events_json(conn, CONFIG, out, today=date(2026, 9, 1))

    data = json.loads(out.read_text(encoding="utf-8"))
    titles = [e["title"] for e in data["events"]]
    assert count == 2
    assert "Future Concert" in titles
    assert "Undated Exhibition" in titles
    assert "Past Concert" not in titles

    # Past event should now be marked status='past' in the DB, not deleted.
    past = conn.execute("SELECT status FROM events WHERE title = 'Past Concert'").fetchone()
    assert past["status"] == "past"


def test_export_events_json_includes_source_attribution(tmp_path: Path):
    conn = connect(":memory:")
    _insert_event(conn, "Concert", "2026-12-31")

    out = tmp_path / "events.json"
    export_events_json(conn, CONFIG, out, today=date(2026, 9, 1))

    data = json.loads(out.read_text(encoding="utf-8"))
    sources = data["events"][0]["sources"]
    assert sources == [{"source_id": "s1", "source_name": "Source One", "url": "https://example.com/a"}]


def test_export_source_stats_json_computes_rates(tmp_path: Path):
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO source_runs (source_id, status, articles_fetched, articles_new_or_changed, "
        "articles_passed_filter, events_confirmed) VALUES ('s1', 'success', 10, 5, 2, 1)"
    )
    conn.execute(
        "INSERT INTO source_runs (source_id, status, error_message) VALUES ('s1', 'error', 'boom')"
    )
    conn.commit()

    out = tmp_path / "source_stats.json"
    count = export_source_stats_json(conn, CONFIG, out)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert count == 1
    stat = data["sources"][0]
    assert stat["source_id"] == "s1"
    assert stat["articles_new_or_changed"] == 5
    assert stat["articles_passed_filter"] == 2
    assert stat["pass_rate"] == 0.4
    assert stat["confirm_rate"] == 0.5
    assert stat["last_error"] == "boom"


def test_export_includes_translations(tmp_path: Path):
    conn = connect(":memory:")
    event_id = _insert_event(conn, "Koncert", "2026-12-31")
    for lang, title in [("en", "Concert"), ("bg", "Концерт")]:
        conn.execute(
            "INSERT INTO event_translations (event_id, lang, title, description) VALUES (?, ?, ?, '')",
            (event_id, lang, title),
        )
    conn.commit()

    out = tmp_path / "events.json"
    export_events_json(conn, CONFIG, out, today=date(2026, 9, 1))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["events"][0]["translations"]["bg"]["title"] == "Концерт"
    assert data["events"][0]["translations"]["en"]["title"] == "Concert"
