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
    if resp.encoding == "ISO-8859-1":
        # requests falls back to ISO-8859-1 per RFC 2616 when a server sends
        # no charset in its Content-Type header. That default silently
        # mangles any non-Latin-1 page (found on moreto.net, which is
        # actually windows-1251) into mojibake -- detect the real encoding
        # instead whenever requests couldn't find one declared.
        resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "lxml")

    # Some sites write internal links meant to resolve against the site
    # root rather than the current page path (e.g. a link literally reading
    # "bg/novini/x" on a page already at "/bg/novini") -- selectors.base_url
    # lets a source override what urljoin resolves relative hrefs against.
    link_base = selectors.get("base_url", source_url)

    link_attr = selectors.get("link_attr", "href")

    items = []
    for node in soup.select(selectors["list_item"]):
        # Some sites make the whole list item an <a> itself (no nested link
        # to select) -- fall back to the node itself when it already carries
        # the link attribute directly.
        if node.name == "a" and node.has_attr(link_attr):
            link_el = node
        else:
            link_el = node.select_one(selectors.get("link", "a"))
        href = link_el.get(link_attr) if link_el else None
        if not href:
            continue
        url = urljoin(link_base, href)

        title_el = node.select_one(selectors["title"]) if selectors.get("title") else link_el
        title = title_el.get_text(" ", strip=True) if title_el else ""
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
