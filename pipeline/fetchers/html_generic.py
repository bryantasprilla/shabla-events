"""CSS-selector-driven HTML fetcher, used for both 'html-article-list' and
'structured-calendar' source types (same mechanics; see AGENTS.md)."""
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from pipeline.fetchers.base import RawItem


def fetch_html(
    source_url: str,
    selectors: dict,
    timeout_s: int = 20,
    user_agent: str = "shabla-events-bot/1.0",
) -> list[RawItem]:
    resp = requests.get(source_url, timeout=timeout_s, headers={"User-Agent": user_agent})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    items = []
    for node in soup.select(selectors["list_item"]):
        link_el = node.select_one(selectors.get("link", "a"))
        href = link_el.get(selectors.get("link_attr", "href")) if link_el else None
        if not href:
            continue
        url = urljoin(source_url, href)

        title_el = node.select_one(selectors["title"]) if selectors.get("title") else link_el
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        # Structured-calendar sources often have no separate description in
        # the listing -- fall back to concatenating date/time/location so
        # there's still something for the relevance filter and LLM to read.
        fallback_parts = []
        for key in ("date", "time", "location"):
            sel = selectors.get(key)
            if not sel:
                continue
            el = node.select_one(sel)
            if el:
                fallback_parts.append(el.get_text(strip=True))

        body = ""
        if selectors.get("body"):
            body_el = node.select_one(selectors["body"])
            if body_el:
                body = body_el.get_text(" ", strip=True)
        if not body:
            body = " | ".join(fallback_parts)

        items.append(RawItem(url=url, title=title, body=body))
    return items
