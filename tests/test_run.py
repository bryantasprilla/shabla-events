from unittest.mock import Mock, patch

from pipeline.config import Settings, Source
from pipeline.db import connect
from pipeline.fetchers.base import RawItem
from pipeline.llm.extractor import ExtractionResult
from pipeline.run import run_source

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
