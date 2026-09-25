# Shabla Events

Scrapes local news and event-calendar sites near Shabla, Bulgaria (and southeastern Romania, Constanța and south) daily, extracts real-world events with a self-hosted LLM, and publishes them as a public page. Runs at $0 recurring cost via GitHub Actions + GitHub Pages.

See [AGENTS.md](AGENTS.md) for architecture and conventions, and [PLAN.md](PLAN.md) for the full design and build-order milestones.

## Status

Milestones 1-9 of 12 complete (scaffold, DB, sources/admin CLI, fetchers,
change detection, relevance filter, LLM extraction, dedup, export/UI) —
see PLAN.md. Verified end to end against real data: the pipeline has
actually run against all 21 configured sources and produced real
extracted, deduplicated events. Remaining: GitHub Issue auto-filing for
failing sources, the GitHub Actions daily workflow, and the calibration
soak period.

## Local development

Requires Python 3.11+. On Windows, install `llama-cpp-python` with
`--prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`
(see requirements.txt) to avoid a MAX_PATH build failure. The model
weights (`models/qwen2.5-7b-instruct-q4_k_m.gguf`, ~4.68GB) aren't part of
`pip install` — download separately from
[bartowski/Qwen2.5-7B-Instruct-GGUF](https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF).

```
pip install -r requirements-dev.txt
python -m pipeline.run --help
python manage.py list-sources
python -m pytest tests/
```

To preview the static pages locally: `python -m http.server 8000` from
inside `docs/`, then open `http://localhost:8000/`.
