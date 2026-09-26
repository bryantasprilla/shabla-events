from pathlib import Path

import pytest

from pipeline.translator import (
    DEFAULT_MODEL_DIR,
    _normalize_input,
    _normalize_output,
    _restore_times,
    detect_language,
)


def test_typographic_quotes_are_normalized_before_translation():
    assert _normalize_input("СУ „Асен Златаров“") == 'СУ "Асен Златаров"'


def test_output_cleanup_removes_unknown_token_marks_and_fixes_romanian_diacritics():
    assert _normalize_output("SU  ⁇ Asen ⁇ school", "en") == "SU Asen school"
    assert _normalize_output("şcoală şi învăţământ Ţara", "ro") == "școală și învățământ Țara"
    # cedilla forms are only rewritten for Romanian output
    assert _normalize_output("şcoală", "en") == "şcoală"


def test_restore_times_fixes_a_shifted_clock_time():
    assert _restore_times("începe la ora 23:00", "starts at 11:00") == "starts at 23:00"
    assert _restore_times("de la 10:00 la 12:30", "from 09:00 to 12:30") == "from 10:00 to 12:30"


def test_restore_times_leaves_correct_or_uncomparable_output_alone():
    assert _restore_times("la 23:00", "at 23:00") == "at 23:00"
    assert _restore_times("no times here", "nothing") == "nothing"
    # different counts: ambiguous, so don't guess
    assert _restore_times("la 23:00", "at 11:00 and 12:00") == "at 11:00 and 12:00"


def test_detect_language():
    assert detect_language("Празникът на село Селце") == "bg"
    assert detect_language("Festivalul Toamnei în Mangalia") == "ro"
    assert detect_language("1234 !!!", fallback="ro") == "ro"


MODEL_PRESENT = (Path(__file__).parent.parent / DEFAULT_MODEL_DIR / "model.bin").exists()


@pytest.mark.skipif(not MODEL_PRESENT, reason="translation model not downloaded")
def test_real_model_translates_all_three_languages():
    from pipeline.translator import Translator

    out = Translator(Path(__file__).parent.parent / DEFAULT_MODEL_DIR).translate(
        "Festivalul Toamnei în Mangalia", "Festivalul se va desfășura pe 15 octombrie la ora 18:00.", "ro"
    )
    assert out["ro"]["title"] == "Festivalul Toamnei în Mangalia"  # source language copied unchanged
    assert "festival" in out["en"]["title"].lower()
    assert "фестивал" in out["bg"]["title"].lower()
    assert "18:00" in out["en"]["description"] or "6:00" in out["en"]["description"]
    assert "Autumn" in out["en"]["title"]
