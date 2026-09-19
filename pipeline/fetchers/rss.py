"""RSS/Atom fetcher, used for source type 'rss'."""
import feedparser
from bs4 import BeautifulSoup

from pipeline.fetchers.base import RawItem


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    return BeautifulSoup(raw, "lxml").get_text(" ", strip=True)


def fetch_rss(source_url: str, timeout_s: int = 20, user_agent: str = "shabla-events-bot/1.0") -> list[RawItem]:
    parsed = feedparser.parse(
        source_url,
        request_headers={"User-Agent": user_agent},
    )
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"failed to parse feed at {source_url}: {parsed.bozo_exception}")

    items = []
    for entry in parsed.entries:
        url = entry.get("link", "")
        title = entry.get("title", "")
        body = _strip_html(entry.get("summary", "") or entry.get("description", ""))
        published_at = entry.get("published", None)
        if url and title:
            items.append(RawItem(url=url, title=title, body=body, published_at=published_at))
    return items
