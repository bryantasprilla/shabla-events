"""Dedicated machine-translation step for event titles/descriptions.

Uses MADLAD-400 3B (Google, T5-based, **Apache-2.0**) via CTranslate2 int8
instead of the general Qwen model: a purpose-built translation model that is
much faster on CPU and translates meanings rather than transliterating.
CTranslate2 + sentencepiece only -- no PyTorch/transformers dependency.

License note: Apache-2.0, so usable commercially. (An earlier version used
NLLB-200, whose weights are CC-BY-NC-4.0 / non-commercial -- replaced for
that reason.) MADLAD is steered by a target-language token prefix
("<2en> text"); it has no source-language tag.
"""
import re
from pathlib import Path

import ctranslate2
import sentencepiece as spm

LANGS = ["en", "bg", "ro"]

# Stored in event_translations.engine; changing the engine/model bumps this so
# older translations are automatically redone.
ENGINE = "madlad400-3b"

DEFAULT_MODEL_DIR = "models/madlad400-3b-mt-ct2-int8"


def detect_language(text: str, fallback: str = "bg") -> str:
    """Cheap script-based guess used only when a source language isn't known:
    Cyrillic -> Bulgarian; otherwise Romanian if it has Romanian letters."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return fallback
    cyrillic = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    if cyrillic / len(letters) > 0.5:
        return "bg"
    if any(c in "ăâîșțşţĂÂÎȘȚŞŢ" for c in text):
        return "ro"
    return fallback


_QUOTE_MAP = str.maketrans({
    "„": '"', "“": '"', "”": '"', "«": '"', "»": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'",
})
_CEDILLA_TO_COMMA = str.maketrans({"ş": "ș", "ţ": "ț", "Ş": "Ș", "Ţ": "Ț"})
_TIME_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b")


def _normalize_input(text: str) -> str:
    # Typographic quotes (esp. Bulgarian „ “) were out-of-vocabulary for the
    # NLLB model tried first (decoded as " ⁇ "); MADLAD copes, but plain
    # quotes are the safe input, so this cheap normalization stays.
    return text.translate(_QUOTE_MAP)


def _normalize_output(text: str, tgt: str) -> str:
    text = re.sub(r"\s+", " ", text.replace("⁇", ""))
    if tgt == "ro":
        # Defensive: NLLB emitted legacy cedilla forms (ş/ţ); Romanian
        # standard is comma-below (ș/ț). MADLAD already does this correctly.
        text = text.translate(_CEDILLA_TO_COMMA)
    return text.strip()


def _restore_times(source: str, translated: str) -> str:
    """Cheap guard against a translation model rewriting a clock time (NLLB
    turned "23:00" into "11:00"; MADLAD got it right in testing). A wrong
    time on an events site is worse than an awkward sentence, so when the
    source and translation contain the same number of HH:MM times but they
    differ, put the source's times back."""
    src_times = _TIME_RE.findall(source)
    out_times = _TIME_RE.findall(translated)
    if not src_times or len(src_times) != len(out_times) or src_times == out_times:
        return translated
    it = iter(src_times)
    return _TIME_RE.sub(lambda _m: next(it), translated)


class Translator:
    def __init__(self, model_dir: str | Path = DEFAULT_MODEL_DIR):
        model_dir = Path(model_dir)
        self._sp = spm.SentencePieceProcessor()
        self._sp.load(str(model_dir / "spiece.model"))
        self._ct2 = ctranslate2.Translator(str(model_dir), device="cpu", compute_type="int8")

    def _translate_texts(self, texts: list[str], tgt: str) -> list[str]:
        """Translates non-empty texts into `tgt` in one batch (order preserved)."""
        if not texts:
            return []
        batch = [
            self._sp.encode(f"<2{tgt}> {_normalize_input(t)}", out_type=str) + ["</s>"] for t in texts
        ]
        results = self._ct2.translate_batch(batch, beam_size=4, max_decoding_length=256)
        out = []
        for source_text, r in zip(texts, results):
            decoded = _normalize_output(self._sp.decode(r.hypotheses[0]), tgt)
            out.append(_restore_times(source_text, decoded))
        return out

    def translate(self, title: str, description: str, src_lang: str) -> dict[str, dict[str, str]]:
        """Returns {lang: {"title", "description"}} for en/bg/ro. The source
        language's text is copied unchanged; the other two are translated."""
        result = {src_lang: {"title": title, "description": description or ""}}
        for tgt in LANGS:
            if tgt == src_lang:
                continue
            texts = [title] + ([description] if description else [])
            translated = self._translate_texts(texts, tgt)
            result[tgt] = {
                "title": translated[0],
                "description": translated[1] if description else "",
            }
        return result
