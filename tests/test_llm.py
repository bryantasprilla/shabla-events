import json
from datetime import date

from llama_cpp import LlamaGrammar

from pipeline.llm.extractor import JSON_SCHEMA
from pipeline.llm.prompt import MAX_BODY_CHARS, build_user_prompt


def test_json_schema_builds_a_grammar():
    # Doesn't need a model loaded -- just confirms the schema itself is valid.
    grammar = LlamaGrammar.from_json_schema(json.dumps(JSON_SCHEMA))
    assert grammar is not None


def test_build_user_prompt_truncates_long_body():
    long_body = "x" * (MAX_BODY_CHARS + 500)
    prompt = build_user_prompt("Source", "https://example.com", "Title", long_body, today=date(2026, 9, 25))
    assert len(prompt) < len(long_body) + 200
    assert "x" * MAX_BODY_CHARS in prompt
    assert "x" * (MAX_BODY_CHARS + 1) not in prompt


def test_build_user_prompt_includes_fields():
    prompt = build_user_prompt("Shabla.bg", "https://shabla.bg/x", "Concert", "Details here", today=date(2026, 9, 25))
    assert "2026-09-25" in prompt
    assert "Shabla.bg" in prompt
    assert "https://shabla.bg/x" in prompt
    assert "Concert" in prompt
    assert "Details here" in prompt
