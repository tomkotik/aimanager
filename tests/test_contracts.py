from __future__ import annotations

from src.core.config_loader import load_tenant_config
from src.core.contracts import ContractValidator
from src.core.intent_router import IntentRouter


def _validator() -> tuple[ContractValidator, IntentRouter]:
    cfg = load_tenant_config("tenants/j-one-studio")
    return ContractValidator(cfg.agent.style), IntentRouter(cfg.dialogue_policy.intents)


def test_pricing_contract_ok():
    validator, router = _validator()
    contract = router.get_intent_config("PRICING").contract  # type: ignore[union-attr]
    result = validator.validate("Стоимость 4990₽/час", contract)
    assert result.ok is True


def test_pricing_contract_must_include_fails():
    validator, router = _validator()
    contract = router.get_intent_config("PRICING").contract  # type: ignore[union-attr]
    result = validator.validate("Стоимость указана на сайте", contract)
    assert result.ok is False
    assert any("must_include" in v for v in result.violations)


def test_pricing_contract_forbidden_fails():
    validator, router = _validator()
    contract = router.get_intent_config("PRICING").contract  # type: ignore[union-attr]
    result = validator.validate("4990₽, адрес: Нижняя Сыромятническая", contract)
    assert result.ok is False
    assert any("forbidden" in v for v in result.violations)


def test_address_contract_ok():
    validator, router = _validator()
    contract = router.get_intent_config("ADDRESS").contract  # type: ignore[union-attr]
    result = validator.validate("Адрес: Нижняя Сыромятническая 11", contract)
    assert result.ok is True


def test_address_contract_forbidden_price_fails():
    validator, router = _validator()
    contract = router.get_intent_config("ADDRESS").contract  # type: ignore[union-attr]
    result = validator.validate("Цена 4990₽, адрес: Нижняя Сыромятническая 11", contract)
    assert result.ok is False
    assert any("forbidden" in v for v in result.violations)


def test_rooms_contract_ok():
    validator, router = _validator()
    contract = router.get_intent_config("ROOMS").contract  # type: ignore[union-attr]
    result = validator.validate("У нас есть Агат и Карелия", contract)
    assert result.ok is True


def test_max_sentences_enforced():
    validator, _ = _validator()
    text = "One. Two. Three. Four. Five."
    result = validator.validate(text, contract=None)
    assert result.ok is False
    assert any("max_sentences" in v for v in result.violations)


def test_max_questions_enforced():
    validator, _ = _validator()
    result = validator.validate("One? Two?", contract=None)
    assert result.ok is False
    assert any("max_questions" in v for v in result.violations)


def test_without_contract_only_style_is_checked():
    validator, _ = _validator()
    result = validator.validate("One. Two. Three.", contract=None)
    assert result.ok is True


def test_empty_text_ok_without_contract():
    validator, _ = _validator()
    result = validator.validate("", contract=None)
    assert result.ok is True

