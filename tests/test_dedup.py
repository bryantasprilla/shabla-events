from pipeline.db import connect
from pipeline.dedup import dedup_and_store, dates_compatible, normalize_title, same_location
from pipeline.llm.extractor import ExtractionResult


def _extraction(title, event_date, location="", description="", time="", source_url="https://example.com/a"):
    return ExtractionResult(
        is_event=True, title=title, date=event_date, time=time, location=location,
        category="concert", description=description, source_url=source_url, raw_response="{}",
    )


def test_normalize_title_strips_diacritics_and_punctuation():
    assert normalize_title("Concert în Constanța!") == normalize_title("Concert in Constanta")


def test_dates_compatible_tolerates_missing_and_close_dates():
    assert dates_compatible("", "2026-10-10") is True
    assert dates_compatible("2026-10-10", "2026-10-11") is True
    assert dates_compatible("2026-10-10", "2027-10-10") is False


def test_same_location_tolerates_missing_and_matches_geo_tag():
    assert same_location("", "Varna") is True
    assert same_location("Плаж Варна", "гр. Варна") is True
    assert same_location("Sofia", "Varna") is False


def test_same_event_from_two_sources_merges_into_one_canonical_event():
    conn = connect(":memory:")
    e1 = _extraction("Concert in the Park", "2026-10-10", location="Varna",
                      description="Short.", source_url="https://source-a.com/1")
    e2 = _extraction("Concert In The Park!", "2026-10-10", location="Varna",
                      description="A much longer and more detailed description of the concert.",
                      time="19:00", source_url="https://source-b.com/2")

    id1 = dedup_and_store(conn, e1, article_id=1, source_id="source_a")
    id2 = dedup_and_store(conn, e2, article_id=2, source_id="source_b")

    assert id1 == id2
    events = conn.execute("SELECT * FROM events").fetchall()
    assert len(events) == 1
    # "most complete wins" backfill: missing time filled in, longer description wins.
    assert events[0]["event_time"] == "19:00"
    assert "detailed" in events[0]["description"]

    sources = conn.execute("SELECT * FROM event_sources WHERE event_id = ?", (id1,)).fetchall()
    assert len(sources) == 2


def test_similar_title_but_different_year_does_not_merge():
    conn = connect(":memory:")
    e1 = _extraction("Annual Kite Festival", "2025-08-15", location="Shabla")
    e2 = _extraction("Annual Kite Festival", "2026-08-15", location="Shabla")

    id1 = dedup_and_store(conn, e1, article_id=1, source_id="s1")
    id2 = dedup_and_store(conn, e2, article_id=2, source_id="s1")

    assert id1 != id2
    events = conn.execute("SELECT * FROM events").fetchall()
    assert len(events) == 2
