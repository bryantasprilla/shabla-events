"""Admin CLI for sources.yaml.

Per AGENTS.md: sources.yaml + this CLI is the whole admin interface -- no
hosted UI, no auth system. Git push access is admin access.
"""
from __future__ import annotations

import argparse
import json
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import Config, Source, load_config, save_config, validate
from pipeline.fetchers.html_generic import fetch_html
from pipeline.fetchers.rss import fetch_rss

DEFAULT_SOURCES_PATH = "sources.yaml"


def _fetch_for_test(source, settings) -> list:
    if source.type == "rss":
        return fetch_rss(source.url, timeout_s=settings.request_timeout_s, user_agent=settings.user_agent)
    return fetch_html(
        source.url,
        source.selectors or {},
        timeout_s=settings.request_timeout_s,
        user_agent=settings.user_agent,
    )


def cmd_test_source(args: argparse.Namespace) -> None:
    config = load_config(args.sources)
    source = next((s for s in config.sources if s.id == args.source_id), None)
    if source is None:
        print(f"ERROR: no source with id '{args.source_id}'")
        sys.exit(1)

    print(f"Fetching {source.id} ({source.type}): {source.url}")
    try:
        items = _fetch_for_test(source, config.settings)
    except Exception as e:
        print(f"ERROR: fetch failed: {e}")
        sys.exit(1)

    print(f"{len(items)} item(s) found")
    if items:
        empty_titles = sum(1 for i in items if not i.title)
        empty_bodies = sum(1 for i in items if not i.body)
        if empty_titles:
            print(f"WARNING: {empty_titles}/{len(items)} item(s) had an empty title")
        if empty_bodies:
            print(f"WARNING: {empty_bodies}/{len(items)} item(s) had an empty body")

    for item in items[:3]:
        body_preview = item.body[:200] + ("..." if len(item.body) > 200 else "")
        print("---")
        print(f"title: {item.title}")
        print(f"url: {item.url}")
        if item.published_at:
            print(f"published_at: {item.published_at}")
        print(f"body: {body_preview}")


def cmd_list_sources(args: argparse.Namespace) -> None:
    config = load_config(args.sources)
    sources = config.sources
    if args.tier is not None:
        sources = [s for s in sources if s.tier == args.tier]
    if args.type is not None:
        sources = [s for s in sources if s.type == args.type]
    if args.active_only:
        sources = [s for s in sources if s.active]

    if args.format == "json":
        print(json.dumps([s.to_dict() for s in sources], indent=2))
        return

    if not sources:
        print("No sources match.")
        return
    width_id = max(len(s.id) for s in sources)
    width_name = max(len(s.name) for s in sources)
    for s in sources:
        flag = "" if s.active else " [inactive]"
        print(f"{s.id:<{width_id}}  T{s.tier}  {s.type:<20}  {s.name:<{width_name}}{flag}")


def cmd_validate(args: argparse.Namespace) -> None:
    config = load_config(args.sources)
    errors = validate(config)
    hard_errors = [e for e in errors if not e.startswith("WARNING")]
    warnings = [e for e in errors if e.startswith("WARNING")]

    for w in warnings:
        print(w)
    for e in hard_errors:
        print(f"ERROR {e}")

    if hard_errors:
        print(f"\n{len(hard_errors)} error(s), {len(warnings)} warning(s).")
        sys.exit(1)
    print(f"OK: {len(config.sources)} source(s) valid ({len(warnings)} warning(s)).")


def cmd_add_source(args: argparse.Namespace) -> None:
    config = load_config(args.sources)
    if any(s.id == args.id for s in config.sources):
        print(f"ERROR: source id '{args.id}' already exists")
        sys.exit(1)
    if any(s.url == args.url for s in config.sources):
        print(f"ERROR: source url '{args.url}' already exists")
        sys.exit(1)

    selectors = json.loads(args.selectors_json) if args.selectors_json else None
    new_source = Source(
        id=args.id,
        name=args.name,
        tier=args.tier,
        type=args.type,
        url=args.url,
        active=not args.inactive,
        geo_tags=args.geo_tags.split(",") if args.geo_tags else [],
        assume_in_range=args.assume_in_range,
        skip_keyword_filter=args.skip_keyword_filter,
        selectors=selectors,
    )

    trial_config = Config(settings=config.settings, sources=config.sources + [new_source])
    errors = [e for e in validate(trial_config) if not e.startswith("WARNING")]
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        sys.exit(1)

    # NOTE: the dry-run test-fetch against the real fetcher code lands in
    # Milestone 4 once pipeline/fetchers/ exists. For now this only
    # validates the config shape before writing.
    print(f"Would add source: {new_source.to_dict()}")
    if args.dry_run:
        print("(dry run, nothing written)")
        return
    if not args.yes:
        confirm = input("Add this source? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    config.sources.append(new_source)
    save_config(args.sources, config)
    print(f"Added '{args.id}' to {args.sources}")


def cmd_remove_source(args: argparse.Namespace) -> None:
    config = load_config(args.sources)
    match = next((s for s in config.sources if s.id == args.id), None)
    if match is None:
        print(f"ERROR: no source with id '{args.id}'")
        sys.exit(1)
    if not args.yes:
        confirm = input(f"Remove source '{args.id}'? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return
    config.sources = [s for s in config.sources if s.id != args.id]
    save_config(args.sources, config)
    print(f"Removed '{args.id}' from {args.sources} (historical DB rows are kept)")


def _set_active(args: argparse.Namespace, active: bool) -> None:
    config = load_config(args.sources)
    match = next((s for s in config.sources if s.id == args.id), None)
    if match is None:
        print(f"ERROR: no source with id '{args.id}'")
        sys.exit(1)
    match.active = active
    save_config(args.sources, config)
    print(f"{'Activated' if active else 'Deactivated'} '{args.id}'")


def cmd_activate_source(args: argparse.Namespace) -> None:
    _set_active(args, True)


def cmd_deactivate_source(args: argparse.Namespace) -> None:
    _set_active(args, False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="shabla-events admin CLI")
    parser.add_argument("--sources", default=DEFAULT_SOURCES_PATH)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-sources")
    p_list.add_argument("--tier", type=int)
    p_list.add_argument("--type")
    p_list.add_argument("--active-only", action="store_true")
    p_list.add_argument("--format", choices=["table", "json"], default="table")
    p_list.set_defaults(func=cmd_list_sources)

    p_validate = sub.add_parser("validate")
    p_validate.set_defaults(func=cmd_validate)

    p_test = sub.add_parser("test-source")
    p_test.add_argument("source_id")
    p_test.set_defaults(func=cmd_test_source)

    p_add = sub.add_parser("add-source")
    p_add.add_argument("--id", required=True)
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--url", required=True)
    p_add.add_argument("--tier", type=int, required=True)
    p_add.add_argument("--type", required=True)
    p_add.add_argument("--geo-tags", default="")
    p_add.add_argument("--assume-in-range", action="store_true")
    p_add.add_argument("--skip-keyword-filter", action="store_true")
    p_add.add_argument("--selectors-json")
    p_add.add_argument("--inactive", action="store_true")
    p_add.add_argument("--dry-run", action="store_true")
    p_add.add_argument("--yes", action="store_true")
    p_add.set_defaults(func=cmd_add_source)

    p_remove = sub.add_parser("remove-source")
    p_remove.add_argument("--id", required=True)
    p_remove.add_argument("--yes", action="store_true")
    p_remove.set_defaults(func=cmd_remove_source)

    p_activate = sub.add_parser("activate-source")
    p_activate.add_argument("--id", required=True)
    p_activate.set_defaults(func=cmd_activate_source)

    p_deactivate = sub.add_parser("deactivate-source")
    p_deactivate.add_argument("--id", required=True)
    p_deactivate.set_defaults(func=cmd_deactivate_source)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
