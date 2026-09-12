"""Daily pipeline orchestrator entrypoint.

Per source: fetch -> change-detect -> relevance-filter -> LLM-extract -> dedup-and-store.
Each source's steps are isolated so one failure never blocks the others (see AGENTS.md).
Not yet implemented beyond argument parsing; filled in across Milestones 2-8.
"""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Shabla Events pipeline orchestrator")
    parser.add_argument("--db", default="data/shabla_events.db")
    parser.add_argument("--sources", default="sources.yaml")
    parser.add_argument("--model", default="models/qwen2.5-7b-instruct-q4_k_m.gguf")
    parser.add_argument("--grammar", default="pipeline/llm/grammar.gbnf")
    parser.parse_args()
    raise SystemExit("pipeline.run is not implemented yet (see PLAN.md, Milestones 2-8)")


if __name__ == "__main__":
    main()
