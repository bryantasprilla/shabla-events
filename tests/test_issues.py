import os
from unittest.mock import Mock, patch

import pytest

from pipeline.config import Config, Settings, Source
from pipeline.db import connect
from pipeline.issues import check_and_file_issues

SOURCE = Source(id="s1", name="Source One", tier=1, type="rss", url="https://example.com", consecutive_failure_threshold=3)
CONFIG = Config(settings=Settings(), sources=[SOURCE])


@pytest.fixture(autouse=True)
def github_env(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "bryantasprilla/shabla-events")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")


def _seed_runs(conn, statuses, error_message="boom"):
    for status in statuses:
        conn.execute(
            "INSERT INTO source_runs (source_id, status, error_message) VALUES (?, ?, ?)",
            ("s1", status, error_message if status == "error" else None),
        )
    conn.commit()


def _mock_response(json_data=None):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = json_data or {}
    return resp


def test_files_issue_after_n_consecutive_failures():
    conn = connect(":memory:")
    _seed_runs(conn, ["error", "error", "error"])

    with patch("pipeline.issues.requests.post", return_value=_mock_response({"number": 42})) as mock_post:
        check_and_file_issues(conn, CONFIG)

    mock_post.assert_called_once()
    assert "issues" in mock_post.call_args[0][0]
    row = conn.execute("SELECT * FROM source_issues WHERE source_id = 's1'").fetchone()
    assert row["github_issue_number"] == 42
    assert row["resolved_at"] is None


def test_does_not_file_a_second_issue_while_one_is_open():
    conn = connect(":memory:")
    _seed_runs(conn, ["error", "error", "error"])
    conn.execute(
        "INSERT INTO source_issues (source_id, github_issue_number, last_commented_at, last_error_text) "
        "VALUES ('s1', 42, datetime('now'), 'boom')"
    )
    conn.commit()

    with patch("pipeline.issues.requests.post") as mock_post:
        check_and_file_issues(conn, CONFIG)

    mock_post.assert_not_called()  # same error, within cooldown -> no new comment either


def test_comments_when_error_message_changes_even_within_cooldown():
    conn = connect(":memory:")
    _seed_runs(conn, ["error", "error", "error"], error_message="new different error")
    conn.execute(
        "INSERT INTO source_issues (source_id, github_issue_number, last_commented_at, last_error_text) "
        "VALUES ('s1', 42, datetime('now'), 'old error')"
    )
    conn.commit()

    with patch("pipeline.issues.requests.post", return_value=_mock_response()) as mock_post:
        check_and_file_issues(conn, CONFIG)

    mock_post.assert_called_once()
    assert "comments" in mock_post.call_args[0][0]


def test_auto_closes_open_issue_on_next_success():
    conn = connect(":memory:")
    _seed_runs(conn, ["error", "error", "error"])
    _seed_runs(conn, ["success"])  # most recent run
    conn.execute(
        "INSERT INTO source_issues (source_id, github_issue_number, last_commented_at, last_error_text) "
        "VALUES ('s1', 42, datetime('now'), 'boom')"
    )
    conn.commit()

    with patch("pipeline.issues.requests.patch", return_value=_mock_response()) as mock_patch:
        check_and_file_issues(conn, CONFIG)

    mock_patch.assert_called_once()
    assert mock_patch.call_args[1]["json"] == {"state": "closed"}
    row = conn.execute("SELECT * FROM source_issues WHERE source_id = 's1'").fetchone()
    assert row["resolved_at"] is not None


def test_no_action_when_not_enough_failure_history():
    conn = connect(":memory:")
    _seed_runs(conn, ["error", "error"])  # only 2, threshold is 3

    with patch("pipeline.issues.requests.post") as mock_post, patch("pipeline.issues.requests.patch") as mock_patch:
        check_and_file_issues(conn, CONFIG)

    mock_post.assert_not_called()
    mock_patch.assert_not_called()
