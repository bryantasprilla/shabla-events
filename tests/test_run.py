from unittest.mock import Mock, patch

from pipeline.config import Settings, Source
from pipeline.db import connect
from pipeline.fetchers.base import RawItem
from pipeline.llm.extractor import ExtractionResult
from pipeline.run import LlmBudget, run_source

SOURCE = Source(id="s1", name="Source 1", tier=1, type="rss", url="https://example.com/feed")
CALENDAR_SOURCE = Source(
    id="s2", name="Source 2", tier=1, type="structured-calendar", url="https://example.com/cal",
    assume_in_range=True, skip_keyword_filter=True,
)
SETTINGS = Settings()


def _mock_extractor(is_event: bool = False):
    extractor = Mock()
    extractor.extract.return_value = ExtractionResult(
        is_event=is_event, title="Some Event", date="2026-10-10", time="18:00",
        location="Shabla", category="concert", description="A description.",
        source_url="https://example.com/a", raw_response="{}",
    )
    return extractor


def test_run_source_logs_success_and_skips_unchanged_on_rerun():
    conn = connect(":memory:")
    items = [RawItem(url="https://example.com/a", title="A", body="Body A")]
    extractor = _mock_extractor()

    with patch("pipeline.run.fetch_source", return_value=items):
        run_source(conn, SOURCE, SETTINGS, extractor)
        run_source(conn, SOURCE, SETTINGS, extractor)

    runs = conn.execute("SELECT * FROM source_runs ORDER BY id").fetchall()
    assert len(runs) == 2
    assert runs[0]["status"] == "success"
    assert runs[0]["articles_new_or_changed"] == 1
    assert runs[1]["articles_new_or_changed"] == 0  # unchanged content on rerun

    articles = conn.execute("SELECT * FROM articles").fetchall()
    assert len(articles) == 1  # upserted, not duplicated
    extractor.extract.assert_not_called()  # "Body A" has no keyword/geo hits -> filtered out


def test_run_source_isolates_errors():
    conn = connect(":memory:")
    extractor = _mock_extractor()

    with patch("pipeline.run.fetch_source", side_effect=RuntimeError("boom")):
        run_source(conn, SOURCE, SETTINGS, extractor)  # must not raise

    runs = conn.execute("SELECT * FROM source_runs").fetchall()
    assert len(runs) == 1
    assert runs[0]["status"] == "error"
    assert "boom" in runs[0]["error_message"]


def test_run_source_extracts_and_dedups_confirmed_events():
    conn = connect(":memory:")
    items = [RawItem(url="https://example.com/a", title="Some Event", body="Details")]
    extractor = _mock_extractor(is_event=True)

    with patch("pipeline.run.fetch_source", return_value=items):
        run_source(conn, CALENDAR_SOURCE, SETTINGS, extractor)

    extractor.extract.assert_called_once()
    run = conn.execute("SELECT * FROM source_runs").fetchone()
    assert run["articles_passed_filter"] == 1
    assert run["events_confirmed"] == 1

    article = conn.execute("SELECT * FROM articles").fetchone()
    assert article["status"] == "event_confirmed"

    events = conn.execute("SELECT * FROM events").fetchall()
    assert len(events) == 1
    assert events[0]["title"] == "Some Event"


def test_llm_budget_defers_excess_articles_to_next_run():
    conn = connect(":memory:")
    items = [RawItem(url=f"https://example.com/{i}", title=f"Event {i}", body="Details") for i in range(3)]
    extractor = _mock_extractor(is_event=True)
    budget = LlmBudget(remaining=2)

    with patch("pipeline.run.fetch_source", return_value=items):
        run_source(conn, CALENDAR_SOURCE, SETTINGS, extractor, budget)

    assert extractor.extract.call_count == 2
    statuses = sorted(r["status"] for r in conn.execute("SELECT status FROM articles").fetchall())
    assert statuses == ["event_confirmed", "event_confirmed", "sent_to_llm"]  # 3rd deferred, not dropped

    # Next run (fresh budget) picks up the deferred article without re-fetching it as new.
    extractor2 = _mock_extractor(is_event=True)
    with patch("pipeline.run.fetch_source", return_value=items):
        run_source(conn, CALENDAR_SOURCE, SETTINGS, extractor2, LlmBudget(remaining=10))
    assert extractor2.extract.call_count == 1
    assert all(r["status"] == "event_confirmed" for r in conn.execute("SELECT status FROM articles").fetchall())


def test_one_failing_extraction_does_not_abort_the_source():
    conn = connect(":memory:")
    items = [RawItem(url=f"https://example.com/{i}", title=f"Event {i}", body="Details") for i in range(3)]
    good = _mock_extractor(is_event=True).extract.return_value
    extractor = Mock()
    extractor.extract.side_effect = [good, ValueError("truncated"), good]

    with patch("pipeline.run.fetch_source", return_value=items):
        run_source(conn, CALENDAR_SOURCE, SETTINGS, extractor)

    run = conn.execute("SELECT * FROM source_runs").fetchone()
    assert run["status"] == "success"  # source not aborted
    statuses = sorted(r["status"] for r in conn.execute("SELECT status FROM articles").fetchall())
    assert statuses == ["error", "event_confirmed", "event_confirmed"]


def test_translate_pending_events_stores_all_languages_and_skips_done():
    from pipeline.run import translate_pending_events

    conn = connect(":memory:")
    conn.execute("INSERT INTO events (title, event_date, description, dedup_key) VALUES ('Koncert', '2999-01-01', 'Opisanie', 'k')")
    conn.execute("INSERT INTO events (title, event_date, description, dedup_key) VALUES ('Old', '2000-01-01', 'x', 'o')")
    conn.commit()
    extractor = Mock()
    extractor.translate.return_value = {
        "en": {"title": "Concert", "description": "Description"},
        "bg": {"title": "Концерт", "description": "Описание"},
        "ro": {"title": "Concert", "description": "Descriere"},
    }

    assert translate_pending_events(conn, extractor, limit=10) == 1  # past event ignored
    rows = {r["lang"]: r["title"] for r in conn.execute("SELECT lang, title FROM event_translations").fetchall()}
    assert rows == {"en": "Concert", "bg": "Концерт", "ro": "Concert"}

    extractor.translate.reset_mock()
    assert translate_pending_events(conn, extractor, limit=10) == 0  # already translated
    extractor.translate.assert_not_called()


def test_translation_failure_is_skipped_not_fatal():
    from pipeline.run import translate_pending_events

    conn = connect(":memory:")
    conn.execute("INSERT INTO events (title, event_date, description, dedup_key) VALUES ('A', '2999-01-01', '', 'a')")
    conn.commit()
    extractor = Mock()
    extractor.translate.side_effect = ValueError("truncated")
    assert translate_pending_events(conn, extractor, limit=10) == 0
    assert conn.execute("SELECT COUNT(*) FROM event_translations").fetchone()[0] == 0
