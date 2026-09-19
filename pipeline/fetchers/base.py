"""Shared fetch result type. rss.py and html_generic.py both return list[RawItem]."""
from dataclasses import dataclass


@dataclass
class RawItem:
    url: str
    title: str
    body: str
    published_at: str | None = None
