from pathlib import Path
from unittest.mock import Mock, patch

from pipeline.fetchers.html_generic import fetch_html

FIXTURES = Path(__file__).parent / "fixtures"

SELECTORS = {
    "list_item": "article.lsvr_event",
    "link": "h3.post__title a",
    "link_attr": "href",
    "title": "h3.post__title a",
    "date": "li.post__info-item--date",
    "time": "li.post__info-item--time",
    "location": "li.post__info-item--location a",
}


def _mock_response(html: str):
    resp = Mock()
    resp.text = html
    resp.raise_for_status = Mock()
    return resp


def test_fetch_html_parses_items_and_resolves_relative_urls():
    html = (FIXTURES / "sample_event_list.html").read_text(encoding="utf-8")
    with patch("pipeline.fetchers.html_generic.requests.get", return_value=_mock_response(html)):
        items = fetch_html("https://shabla.bg/events/", SELECTORS)

    assert len(items) == 2
    assert items[0].title == "Example Concert"
    assert items[0].url == "https://shabla.bg/events/example-concert/"
    assert "10/10/2026" in items[0].body
    assert "Town Park" in items[0].body

    # Second item's link is already absolute -- urljoin must leave it alone.
    assert items[1].url == "https://example.com/events/other/"
    # No location selector match -> falls back to just the date.
    assert items[1].body == "11/10/2026"


def test_fetch_html_skips_items_with_no_link():
    html = "<article class='lsvr_event'><h3 class='post__title'>No link here</h3></article>"
    with patch("pipeline.fetchers.html_generic.requests.get", return_value=_mock_response(html)):
        items = fetch_html("https://shabla.bg/events/", SELECTORS)
    assert items == []


class _FakeResponse:
    """Mimics requests.Response's lazy, encoding-dependent .text decoding
    (a plain Mock can't do this since .text is normally a property)."""

    def __init__(self, raw_bytes: bytes, encoding: str, apparent_encoding: str):
        self._raw = raw_bytes
        self.encoding = encoding
        self.apparent_encoding = apparent_encoding

    def raise_for_status(self):
        pass

    @property
    def text(self):
        return self._raw.decode(self.encoding)


def test_fetch_html_corrects_undeclared_charset():
    # moreto.net sends no charset header; requests defaults to ISO-8859-1
    # per RFC 2616, which mangles this windows-1251 page into mojibake
    # unless corrected.
    html = "<article class='lsvr_event'><h3 class='post__title'><a href='/x'>Кино прожекция</a></h3></article>"
    fake = _FakeResponse(html.encode("windows-1251"), encoding="ISO-8859-1", apparent_encoding="windows-1251")
    with patch("pipeline.fetchers.html_generic.requests.get", return_value=fake):
        items = fetch_html("https://www.moreto.net/events.php", SELECTORS)
    assert items[0].title == "Кино прожекция"


def test_fetch_html_base_url_override_for_root_relative_links():
    # Some sites write links like "bg/novini/x" meant to resolve against the
    # site root, not the current page path (balchik.bg) -- selectors.base_url
    # overrides what urljoin resolves against.
    html = "<article class='lsvr_event'><h3 class='post__title'><a href='bg/novini/x'>Title</a></h3></article>"
    selectors = {**SELECTORS, "base_url": "https://www.balchik.bg/"}
    with patch("pipeline.fetchers.html_generic.requests.get", return_value=_mock_response(html)):
        items = fetch_html("https://www.balchik.bg/bg/novini", selectors)
    assert items[0].url == "https://www.balchik.bg/bg/novini/x"
