"""Cheap pre-screen run before anything reaches the LLM (Milestone 6).

Two signals combine into a pass/fail gate per article:
  1. A bilingual weighted keyword hit-count (title hits count more than body
     hits) plus a date/time regex bonus.
  2. A geo place-name gate (pipeline/geo.py) -- this is what keeps
     high-volume city sources (Varna, Constanta) from flooding the LLM step.

Structured-calendar sources (skip_keyword_filter=True) skip signal 1 --
every entry there is already an event -- but still need a geo match unless
assume_in_range is set.

NOTE on keyword scoring: the original design (see PLAN.md) called for
SQLite FTS5's bm25() ranking function, mirroring Elasticsearch-style
relevancy scoring. In practice bm25() is a *corpus-relative* ranking
function: its IDF term degenerates toward zero on a small corpus (a
handful of articles) and drifts as more documents are added to the FTS
index over time, so a fixed absolute threshold isn't stable -- the same
article can score very differently depending on how many other articles
happen to be in the table when it's scored. A simple weighted substring
hit-count against the fixed keyword list is stable and predictable
instead, so that's what's implemented here. articles_fts / bm25 remain
available in the schema for potential future ad-hoc search use, just not
for this gate. KEYWORD_THRESHOLD is a starting constant to be tuned during
the Milestone 12 soak period against real near-miss data.
"""
import re

from pipeline.config import Source
from pipeline.geo import match_geo

KEYWORD_THRESHOLD = 3.0
TITLE_HIT_WEIGHT = 5.0
BODY_HIT_WEIGHT = 1.0

BG_KEYWORDS = [
    "събитие", "концерт", "изложба", "фестивал", "ще се проведе", "заповядайте",
    "начало на", "читалище", "представление", "тържество", "честване", "конкурс",
    "турнир", "спектакъл", "празник", "прожекция", "среща с автор", "работилница",
    "кукерски", "покана", "програма",
]

RO_KEYWORDS = [
    "eveniment", "concert", "festival", "petrecere", "expoziție", "spectacol",
    "se va desfășura", "vă invităm", "atelier", "concurs", "turneu", "sărbătoare",
    "proiecție", "lansare de carte", "program",
]

ALL_KEYWORDS = [kw.lower() for kw in BG_KEYWORDS + RO_KEYWORDS]

_MONTHS_BG = (
    "януари|февруари|март|април|май|юни|юли|август|септември|октомври|ноември|декември"
)
_MONTHS_RO = (
    "ianuarie|februarie|martie|aprilie|mai|iunie|iulie|august|septembrie|octombrie|noiembrie|decembrie"
)
_WEEKDAYS_BG = "понеделник|вторник|сряда|четвъртък|петък|събота|неделя"
_WEEKDAYS_RO = "luni|marți|miercuri|joi|vineri|sâmbătă|duminică"

DATE_REGEX = re.compile(
    r"\d{1,2}\.\d{1,2}\.\d{4}"
    rf"|\d{{1,2}}\s+(?:{_MONTHS_BG})"
    rf"|\d{{1,2}}\s+(?:{_MONTHS_RO})"
    r"|\d{1,2}:\d{2}\s*ч\.?"
    r"|ora\s+\d{1,2}[:.]\d{2}"
    rf"|{_WEEKDAYS_BG}"
    rf"|{_WEEKDAYS_RO}",
    re.IGNORECASE,
)
DATE_BONUS = 2.0


def date_regex_bonus(text: str) -> float:
    return DATE_BONUS if DATE_REGEX.search(text or "") else 0.0


def keyword_score(title: str, body: str) -> float:
    """Weighted count of keyword hits: each keyword found in the title adds
    TITLE_HIT_WEIGHT, each found in the body adds BODY_HIT_WEIGHT."""
    title_lower = (title or "").lower()
    body_lower = (body or "").lower()
    score = 0.0
    for kw in ALL_KEYWORDS:
        if kw in title_lower:
            score += TITLE_HIT_WEIGHT
        if kw in body_lower:
            score += BODY_HIT_WEIGHT
    return score


def evaluate_relevance(title: str, body: str, source: Source) -> tuple[float, list[str], bool]:
    """Returns (relevance_score, geo_matched_tags, passes_filter)."""
    text = f"{title}\n{body}"

    if source.skip_keyword_filter:
        score = 0.0
        keyword_ok = True
    else:
        score = keyword_score(title, body) + date_regex_bonus(text)
        keyword_ok = score >= KEYWORD_THRESHOLD

    if source.assume_in_range:
        geo_matched: list[str] = []
        geo_ok = True
    else:
        geo_matched = match_geo(text)
        geo_ok = bool(geo_matched)

    return score, geo_matched, keyword_ok and geo_ok
