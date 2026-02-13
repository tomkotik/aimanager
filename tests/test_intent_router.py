from __future__ import annotations

from src.core.config_loader import load_tenant_config
from src.core.intent_router import IntentRouter


def _router() -> IntentRouter:
    cfg = load_tenant_config("tenants/j-one-studio")
    return IntentRouter(cfg.dialogue_policy.intents)


def test_pricing():
    assert _router().detect("Сколько стоит съёмка?") == "PRICING"


def test_address():
    assert _router().detect("Где вы находитесь?") == "ADDRESS"


def test_rooms():
    assert _router().detect("Какие залы есть?") == "ROOMS"


def test_greeting():
    assert _router().detect("Привет!") == "GREETING"


def test_booking():
    assert _router().detect("Хочу забронировать") == "BOOKING"


def test_reschedule():
    assert _router().detect("Можно перенести запись?") == "RESCHEDULE"


def test_escalate_discount():
    assert _router().detect("Мне нужна скидку") == "ESCALATE"


def test_fallback():
    assert _router().detect("Расскажите о чём-нибудь") == "SAFE_FAQ"


def test_priority_escalate_over_address():
    assert _router().detect("Срочно нужен адрес") == "ESCALATE"


def test_get_intent_config_pricing_has_contract():
    cfg = load_tenant_config("tenants/j-one-studio")
    router = IntentRouter(cfg.dialogue_policy.intents)
    intent = router.get_intent_config("PRICING")
    assert intent is not None
    assert intent.contract is not None


def test_get_intent_config_nonexistent_returns_none():
    assert _router().get_intent_config("NONEXISTENT") is None

