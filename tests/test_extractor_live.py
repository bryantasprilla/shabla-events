"""Live extraction test against the actual downloaded model weights.

Skipped automatically if the model file isn't present (e.g. a dev machine
that hasn't downloaded it yet) -- runs for real in CI once the weights are
cached/downloaded there (Milestone 11), acting as an ongoing extraction
quality check, not just a one-off Milestone 7 verification.
"""
import time
from datetime import date
from pathlib import Path

import pytest

MODEL_PATH = Path(__file__).parent.parent / "models" / "qwen2.5-7b-instruct-q4_k_m.gguf"

pytestmark = pytest.mark.skipif(not MODEL_PATH.exists(), reason="model weights not downloaded")

from pipeline.llm.extractor import Extractor  # noqa: E402


@pytest.fixture(scope="module")
def extractor():
    return Extractor(str(MODEL_PATH))


def test_bulgarian_event_extraction(extractor):
    start = time.monotonic()
    result = extractor.extract(
        source_name="Shabla.bg",
        source_url="https://shabla.bg/events/example/",
        title="Юбилеен концерт по повод 50 години средно образование в СУ „Асен Златаров“, гр. Шабла",
        body='10/10/2026 | 16:00 | СУ "Асен Златаров", гр. Шабла',
        today=date(2026, 9, 1),
    )
    print(f"\n[latency] bulgarian_event: {time.monotonic() - start:.1f}s -> {result}")
    assert result.is_event is True
    assert result.date == "2026-10-10"
    assert result.time == "16:00"
    assert result.category == "concert"
    assert result.source_url == "https://shabla.bg/events/example/"


def test_bulgarian_non_event_administrative_notice(extractor):
    start = time.monotonic()
    result = extractor.extract(
        source_name="Kavarna.bg",
        source_url="https://www.kavarna.bg/x",
        title="Временно преустановяване на газоподаването на потребители на територията на община Каварна",
        body=(
            'Община Каварна уведомява гражданите и потребителите, че във връзка с писмо на '
            '"Каварна газ" ООД, изх. № 34/26.08.2026 г., на 28.08.2026 г., в часовия диапазон от '
            '08:00 до 17:00 часа, временно ще бъде спряно газоподаването.'
        ),
        today=date(2026, 9, 1),
    )
    print(f"\n[latency] bulgarian_non_event: {time.monotonic() - start:.1f}s -> {result}")
    assert result.is_event is False


def test_romanian_event_extraction(extractor):
    start = time.monotonic()
    result = extractor.extract(
        source_name="MangaliaNews.ro",
        source_url="https://www.mangalianews.ro/x",
        title="Festivalul Toamnei se va desfășura in Mangalia",
        body=(
            "Va invitam la Festivalul Toamnei, care se va desfasura pe 15 octombrie 2026, "
            "ora 18:00, in Parcul Central din Mangalia."
        ),
        today=date(2026, 9, 1),
    )
    print(f"\n[latency] romanian_event: {time.monotonic() - start:.1f}s -> {result}")
    assert result.is_event is True
    assert result.date == "2026-10-15"
    assert result.category == "festival"


def test_adult_18_plus_category(extractor):
    start = time.monotonic()
    result = extractor.extract(
        source_name="Zile si Nopti",
        source_url="https://zilesinopti.ro/x",
        title="Petrecere de neuitat in club, doar 18+",
        body=(
            "Vino la cea mai tare petrecere de noapte din Constanta, sambata 20/09/2026, "
            "incepe la ora 23:00. Acces permis doar persoanelor peste 18 ani."
        ),
        today=date(2026, 9, 1),
    )
    print(f"\n[latency] adult_18_plus: {time.monotonic() - start:.1f}s -> {result}")
    assert result.is_event is True
    assert result.category == "adult_18+"
