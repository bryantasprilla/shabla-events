from pipeline.config import Source
from pipeline.geo import match_geo
from pipeline.relevance import evaluate_relevance

REGIONAL_SOURCE = Source(
    id="regional", name="Regional", tier=4, type="html-article-list",
    url="https://example.com", assume_in_range=False, skip_keyword_filter=False,
)
LOCAL_SOURCE = Source(
    id="local", name="Local", tier=1, type="html-article-list",
    url="https://example.com", assume_in_range=True, skip_keyword_filter=False,
)
CALENDAR_SOURCE = Source(
    id="calendar", name="Calendar", tier=4, type="structured-calendar",
    url="https://example.com", assume_in_range=False, skip_keyword_filter=True,
)


def test_geo_match_finds_bulgarian_and_romanian_places():
    assert "shabla" in match_geo("Новини от Шабла днес")
    assert "mangalia" in match_geo("Eveniment cultural in Mangalia")
    assert match_geo("Nothing relevant here at all") == []


def test_regional_source_needs_both_keyword_and_geo_hit():
    title = "Концерт във Варна"
    body = "Заповядайте на концерт в града довечера от 18:00 ч."
    score, geo, ok = evaluate_relevance(title, body, REGIONAL_SOURCE)
    assert ok is True
    assert "varna" in geo
    assert score > 0


def test_regional_source_fails_without_geo_match():
    title = "Концерт"
    body = "Заповядайте на голям концерт довечера от 18:00 ч."
    _, geo, ok = evaluate_relevance(title, body, REGIONAL_SOURCE)
    assert ok is False
    assert geo == []


def test_regional_source_fails_without_keyword_hit_even_with_geo():
    title = "Пътен ремонт във Варна"
    body = "Общинска администрация уведомява за ремонт на улица."
    _, _, ok = evaluate_relevance(title, body, REGIONAL_SOURCE)
    assert ok is False


def test_local_source_skips_geo_gate():
    title = "Концерт в читалището"
    body = "Заповядайте на концерт тази вечер."
    _, geo, ok = evaluate_relevance(title, body, LOCAL_SOURCE)
    assert ok is True
    assert geo == []  # geo gate skipped entirely for assume_in_range sources


def test_calendar_source_skips_keyword_gate_but_still_needs_geo():
    ok_no_geo = evaluate_relevance("ALICE IN CHAINS TRIBUTE", "Sambata, 19/09/2026", CALENDAR_SOURCE)[2]
    assert ok_no_geo is False  # no keyword needed, but still no geo match

    _, geo, ok = evaluate_relevance("Concert in Varna", "Sambata, 19/09/2026 in Varna", CALENDAR_SOURCE)
    assert ok is True
    assert "varna" in geo
