"""Self-hosted LLM extraction via llama-cpp-python (Milestone 7).

Loads the model once and reuses it across every article in a run. Output
is forced into grammar.gbnf's schema via GBNF grammar-constrained decoding,
so malformed JSON is structurally impossible -- no retry/repair logic is
needed (see AGENTS.md). source_url is always overwritten with the known
article URL after parsing; the model's own url output is never trusted.
"""
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from llama_cpp import Llama, LlamaGrammar

from pipeline.llm.prompt import SYSTEM_PROMPT, build_user_prompt

GRAMMAR_PATH = Path(__file__).parent / "grammar.gbnf"

VALID_CATEGORIES = {
    "concert", "festival", "exhibition", "municipal", "sports", "theater", "adult_18+", "other",
}


@dataclass
class ExtractionResult:
    is_event: bool
    title: str
    date: str
    time: str
    location: str
    category: str
    description: str
    source_url: str
    raw_response: str


class Extractor:
    def __init__(self, model_path: str, grammar_path: str | Path = GRAMMAR_PATH, n_ctx: int = 4096):
        self._llm = Llama(model_path=model_path, n_ctx=n_ctx, verbose=False)
        self._grammar = LlamaGrammar.from_file(str(grammar_path))

    def extract(
        self,
        source_name: str,
        source_url: str,
        title: str,
        body: str,
        today: date | None = None,
    ) -> ExtractionResult:
        user_prompt = build_user_prompt(source_name, source_url, title, body, today)
        response = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            grammar=self._grammar,
            temperature=0,
            max_tokens=300,
        )
        raw = response["choices"][0]["message"]["content"]
        data = json.loads(raw)

        category = data.get("category", "other")
        if category not in VALID_CATEGORIES:
            category = "other"

        return ExtractionResult(
            is_event=bool(data.get("is_event", False)),
            title=data.get("title", ""),
            date=data.get("date", ""),
            time=data.get("time", ""),
            location=data.get("location", ""),
            category=category,
            description=data.get("description", ""),
            source_url=source_url,
            raw_response=raw,
        )
