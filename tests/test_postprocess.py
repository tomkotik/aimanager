from __future__ import annotations

from src.core.postprocess import Postprocessor
from src.core.schemas import AgentStyle, IntentContract


def _pp(max_sentences: int = 3, max_questions: int = 1) -> Postprocessor:
    style = AgentStyle(max_sentences=max_sentences, max_questions=max_questions, clean_text=True)
    return Postprocessor(style)


def test_remove_markdown_bold():
    assert Postprocessor._remove_markdown("**Жирный** текст") == "Жирный текст"


def test_remove_markdown_header():
    assert Postprocessor._remove_markdown("# Заголовок") == "Заголовок"


def test_remove_markdown_link():
    assert Postprocessor._remove_markdown("[ссылка](http://url)") == "ссылка"


def test_remove_fillers_basic():
    pp = _pp()
    assert pp._remove_fillers("Понял. Стоимость 4990₽") == "Стоимость 4990₽"


def test_remove_fillers_multiple():
    pp = _pp()
    assert pp._remove_fillers("Отлично! Давайте посчитаем. Итого 5000₽") == "Итого 5000₽"


def test_enforce_sentence_limit():
    text = "One. Two. Three. Four. Five."
    assert Postprocessor._enforce_sentence_limit(text, max_sentences=3) == "One. Two. Three."


def test_enforce_question_limit():
    text = "Вопрос? Ещё? Третий?"
    assert Postprocessor._enforce_question_limit(text, max_questions=1) == "Вопрос?"


def test_remove_forbidden_lines():
    text = "Первая строка\nАдрес: Нижняя Сыромятническая\nТретья строка"
    out = Postprocessor._remove_forbidden_lines(text, forbidden=["Адрес"], intent_id=None)
    assert "Адрес" not in out
    assert "Первая строка" in out
    assert "Третья строка" in out


def test_full_process_cleans_and_trims():
    pp = _pp(max_sentences=3, max_questions=1)
    text = "**Понял.** Стоимость 4990₽. Второе. Третье. Четвёртое. Пятое?"
    out = pp.process(text)
    assert "**" not in out
    assert out.startswith("Стоимость 4990₽")
    # max_sentences=3 should keep only first 3 sentences.
    assert out.count(".") <= 3


def test_process_empty_string():
    pp = _pp()
    assert pp.process("") == ""


def test_process_without_contract():
    pp = _pp(max_sentences=2, max_questions=1)
    out = pp.process("Понял. **One.** Two. Three?")
    assert "**" not in out
    assert out.startswith("One.")


def test_process_with_contract_removes_forbidden_lines():
    pp = _pp()
    contract = IntentContract(forbidden=["Адрес"], must_include_any=[])
    out = pp.process("Стоимость 4990₽.\nАдрес: ...", intent_id="PRICING", contract=contract)
    assert "Адрес" not in out


def test_prepayment_removed_simple():
    pp = _pp()
    assert pp.process("Предоплата 50% по ссылке.") == ""


def test_prepayment_removed_preserves_other_sentences():
    pp = _pp()
    assert pp.process("Стоимость 4990₽. Предоплата 50%.") == "Стоимость 4990₽."


def test_allow_prepayment_keeps_text():
    pp = _pp()
    assert pp.process("Предоплата 50% по ссылке.", allow_prepayment=True) == "Предоплата 50% по ссылке."


def test_prepayment_removed_avans():
    pp = _pp()
    assert pp.process("Необходимо оплатить аванс.") == ""
