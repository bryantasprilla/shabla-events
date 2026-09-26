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


def test_fetch_html_base_url_override_for_root_relative_links():
    # Some sites write links like "bg/novini/x" meant to resolve against the
    # site root, not the current page path (balchik.bg) -- selectors.base_url
    # overrides what urljoin resolves against.
    html = "<article class='lsvr_event'><h3 class='post__title'><a href='bg/novini/x'>Title</a></h3></article>"
    selectors = {**SELECTORS, "base_url": "https://www.balchik.bg/"}
    with patch("pipeline.fetchers.html_generic.requests.get", return_value=_mock_response(html)):
        items = fetch_html("https://www.balchik.bg/bg/novini", selectors)
    assert items[0].url == "https://www.balchik.bg/bg/novini/x"
