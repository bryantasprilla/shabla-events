"""Loads and validates sources.yaml, and writes it back for manage.py.

sources.yaml is the single source of truth for source config (see AGENTS.md).
Uses ruamel.yaml (round-trip mode) so hand-added comments/formatting survive
programmatic edits from manage.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

from pipeline.geo import GEO_PLACES

VALID_TYPES = {"rss", "html-article-list", "structured-calendar"}
SELECTORS_REQUIRED_FOR = {"html-article-list", "structured-calendar"}

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)


@dataclass
class Source:
    id: str
    name: str
    tier: int
    type: str
    url: str
    active: bool = True
    geo_tags: list[str] = field(default_factory=list)
    assume_in_range: bool = False
    skip_keyword_filter: bool = False
    selectors: dict | None = None
    consecutive_failure_threshold: int | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        return cls(
            id=d["id"],
            name=d["name"],
            tier=d["tier"],
            type=d["type"],
            url=d["url"],
            active=d.get("active", True),
            geo_tags=list(d.get("geo_tags", [])),
            assume_in_range=d.get("assume_in_range", False),
            skip_keyword_filter=d.get("skip_keyword_filter", False),
            selectors=d.get("selectors"),
            consecutive_failure_threshold=d.get("consecutive_failure_threshold"),
        )

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "tier": self.tier,
            "type": self.type,
            "url": self.url,
            "active": self.active,
            "geo_tags": self.geo_tags,
        }
        if self.assume_in_range:
            d["assume_in_range"] = True
        if self.skip_keyword_filter:
            d["skip_keyword_filter"] = True
        if self.selectors:
            d["selectors"] = self.selectors
        if self.consecutive_failure_threshold is not None:
            d["consecutive_failure_threshold"] = self.consecutive_failure_threshold
        return d


@dataclass
class Settings:
    consecutive_failure_threshold: int = 3
    request_timeout_s: int = 20
    user_agent: str = "shabla-events-bot/1.0"


@dataclass
class Config:
    settings: Settings
    sources: list[Source]


def load_config(path: str | Path) -> Config:
    with open(path, encoding="utf-8") as f:
        raw = _yaml.load(f) or {}
    settings_raw = raw.get("settings", {})
    settings = Settings(
        consecutive_failure_threshold=settings_raw.get("consecutive_failure_threshold", 3),
        request_timeout_s=settings_raw.get("request_timeout_s", 20),
        user_agent=settings_raw.get("user_agent", "shabla-events-bot/1.0"),
    )
    sources = [Source.from_dict(s) for s in raw.get("sources", [])]
    return Config(settings=settings, sources=sources)


def save_config(path: str | Path, config: Config) -> None:
    """Round-trip write: only the `sources` list is regenerated; if the file
    already exists its other formatting/comments are preserved."""
    p = Path(path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            raw = _yaml.load(f) or {}
    else:
        raw = {"version": 1, "settings": {}}
    raw["sources"] = [s.to_dict() for s in config.sources]
    with open(p, "w", encoding="utf-8") as f:
        _yaml.dump(raw, f)


def validate(config: Config) -> list[str]:
    """Returns a list of error/warning strings; empty list means valid."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()

    for s in config.sources:
        if s.id in seen_ids:
            errors.append(f"duplicate source id: {s.id}")
        seen_ids.add(s.id)

        if s.url in seen_urls:
            errors.append(f"duplicate source url: {s.url} (id={s.id})")
        seen_urls.add(s.url)

        if s.type not in VALID_TYPES:
            errors.append(f"{s.id}: invalid type '{s.type}' (must be one of {sorted(VALID_TYPES)})")

        if not (1 <= s.tier <= 6):
            errors.append(f"{s.id}: tier must be 1-6, got {s.tier}")

        if s.type in SELECTORS_REQUIRED_FOR and not s.selectors:
            errors.append(f"{s.id}: type '{s.type}' requires 'selectors'")

        for tag in s.geo_tags:
            if tag not in GEO_PLACES:
                errors.append(f"WARNING {s.id}: unrecognized geo_tag '{tag}' (not in pipeline/geo.py)")

    return errors
