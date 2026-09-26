"""Self-hosted LLM extraction via llama-cpp-python (Milestone 7).

Loads the model once and reuses it across every article in a run. Output
is forced into a JSON schema via grammar-constrained decoding, so
malformed JSON is structurally impossible -- no retry/repair logic is
needed for that (see AGENTS.md). source_url is always overwritten with the
known article URL after parsing; the model's own url output is never
trusted.

NOTE: the grammar is built at runtime from JSON_SCHEMA via
LlamaGrammar.from_json_schema(), not loaded from a hand-written .gbnf
file. An earlier hand-written GBNF grammar (enforcing strict YYYY-MM-DD /
HH:MM patterns at the grammar level) passed llama_cpp's shallow
from_file() parse check but caused a native access-violation crash deep in
the sampler when actually used for generation -- a real bug/fragility in
this binding's raw-GBNF path, not just a syntax typo (multiple corrected
variants still crashed). from_json_schema uses llama.cpp's own
json-schema-to-grammar conversion, which is much better tested. The
tradeoff: date/time format is no longer grammar-enforced, so
_normalize_date/_normalize_time validate and blank out anything
malformed after parsing, rather than making it structurally impossible.
"""
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from llama_cpp import Llama, LlamaGrammar

from pipeline.llm.prompt import SYSTEM_PROMPT, build_user_prompt

VALID_CATEGORIES = [
    "concert", "festival", "exhibition", "municipal", "sports", "theater", "adult_18+", "other",
]

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "is_event": {"type": "boolean"},
        "title": {"type": "string"},
        "date": {"type": "string"},
        "time": {"type": "string"},
        "location": {"type": "string"},
        "category": {"type": "string", "enum": VALID_CATEGORIES},
        "description": {"type": "string"},
        "source_url": {"type": "string"},
    },
    "required": ["is_event", "title", "date", "time", "location", "category", "description", "source_url"],
    "additionalProperties": False,
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _normalize_date(value: str) -> str:
    return value if _DATE_RE.match(value or "") else ""


def _normalize_time(value: str) -> str:
    return value if _TIME_RE.match(value or "") else ""


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
    def __init__(self, model_path: str, n_ctx: int = 4096):
        self._llm = Llama(model_path=model_path, n_ctx=n_ctx, verbose=False)
        self._grammar = LlamaGrammar.from_json_schema(json.dumps(JSON_SCHEMA))

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
            max_tokens=700,
        )
        choice = response["choices"][0]
        raw = choice["message"]["content"]
        if choice.get("finish_reason") == "length":
            # Grammar-constrained decoding guarantees valid JSON only if the
            # model finishes; hitting max_tokens truncates mid-string (seen on
            # long Cyrillic descriptions, which are token-heavy).
            raise ValueError(f"model output truncated at max_tokens: {raw[-60:]!r}")
        data = json.loads(raw)

        category = data.get("category", "other")
        if category not in VALID_CATEGORIES:
            category = "other"

        return ExtractionResult(
            is_event=bool(data.get("is_event", False)),
            title=data.get("title", ""),
            date=_normalize_date(data.get("date", "")),
            time=_normalize_time(data.get("time", "")),
            location=data.get("location", ""),
            category=category,
            description=data.get("description", ""),
            source_url=source_url,
            raw_response=raw,
        )
