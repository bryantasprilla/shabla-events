# Shabla Events

Scrapes local news and event-calendar sites near Shabla, Bulgaria (and southeastern Romania, Constanța and south) daily, extracts real-world events with a self-hosted LLM, and publishes them as a public page. Runs at $0 recurring cost via GitHub Actions + GitHub Pages.

See [AGENTS.md](AGENTS.md) for architecture and conventions, and [PLAN.md](PLAN.md) for the full design and build-order milestones.

## Status

Scaffolding in progress (Milestone 1 of 12 — see PLAN.md).

## Local development

Requires Python 3.11+.

```
pip install -r requirements.txt
python -m pipeline.run --help
python manage.py list-sources
```
