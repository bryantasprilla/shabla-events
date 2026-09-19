from unittest.mock import patch

from pipeline.config import Settings, Source
from pipeline.db import connect
from pipeline.fetchers.base import RawItem
from pipeline.run import run_source

SOURCE = Source(id="s1", name="Source 1", tier=1, type="rss", url="https://example.com/feed")
SETTINGS = Settings()


def test_run_source_logs_success_and_skips_unchanged_on_rerun():
    conn = connect(":memory:")
    items = [RawItem(url="https://example.com/a", title="A", body="Body A")]

    with patch("pipeline.run.fetch_source", return_value=items):
        run_source(conn, SOURCE, SETTINGS)
        run_source(conn, SOURCE, SETTINGS)

    runs = conn.execute("SELECT * FROM source_runs ORDER BY id").fetchall()
    assert len(runs) == 2
    assert runs[0]["status"] == "success"
    assert runs[0]["articles_new_or_changed"] == 1
    assert runs[1]["articles_new_or_changed"] == 0  # unchanged content on rerun

    articles = conn.execute("SELECT * FROM articles").fetchall()
    assert len(articles) == 1  # upserted, not duplicated


def test_run_source_isolates_errors():
    conn = connect(":memory:")

    with patch("pipeline.run.fetch_source", side_effect=RuntimeError("boom")):
        run_source(conn, SOURCE, SETTINGS)  # must not raise

    runs = conn.execute("SELECT * FROM source_runs").fetchall()
    assert len(runs) == 1
    assert runs[0]["status"] == "error"
    assert "boom" in runs[0]["error_message"]
