from __future__ import annotations

from src.core.config_loader import load_tenant_config
from src.core.intent_lock import IntentLock


def _intents():
    cfg = load_tenant_config("tenants/j-one-studio")
    return cfg.dialogue_policy.intents


def test_first_message_sets_lock():
    lock = IntentLock(lock_turns=2)
    state: dict = {}
    effective = lock.apply(state, raw_intent="PRICING", intents=_intents())
    assert effective == "PRICING"
    assert state[IntentLock.KEY_LOCKED] == "PRICING"
    assert state[IntentLock.KEY_TURNS_LEFT] == 2


def test_second_turn_lock_holds():
    lock = IntentLock(lock_turns=2)
    state = {IntentLock.KEY_LOCKED: "PRICING", IntentLock.KEY_TURNS_LEFT: 2}
    effective = lock.apply(state, raw_intent="SAFE_FAQ", intents=_intents())
    assert effective == "PRICING"
    assert state[IntentLock.KEY_TURNS_LEFT] == 1


def test_third_turn_lock_holds_to_zero():
    lock = IntentLock(lock_turns=2)
    state = {IntentLock.KEY_LOCKED: "PRICING", IntentLock.KEY_TURNS_LEFT: 1}
    effective = lock.apply(state, raw_intent="SAFE_FAQ", intents=_intents())
    assert effective == "PRICING"
    assert state[IntentLock.KEY_TURNS_LEFT] == 0


def test_fourth_turn_lock_expired():
    lock = IntentLock(lock_turns=2)
    state = {IntentLock.KEY_LOCKED: "PRICING", IntentLock.KEY_TURNS_LEFT: 0}
    effective = lock.apply(state, raw_intent="SAFE_FAQ", intents=_intents())
    assert effective == "SAFE_FAQ"
    assert state[IntentLock.KEY_LOCKED] == "SAFE_FAQ"
    assert state[IntentLock.KEY_TURNS_LEFT] == 2


def test_escalate_always_overrides():
    lock = IntentLock(lock_turns=2)
    state = {IntentLock.KEY_LOCKED: "PRICING", IntentLock.KEY_TURNS_LEFT: 2}
    effective = lock.apply(state, raw_intent="ESCALATE", intents=_intents())
    assert effective == "ESCALATE"
    assert state[IntentLock.KEY_LOCKED] == "ESCALATE"
    assert state[IntentLock.KEY_TURNS_LEFT] == 2


def test_higher_priority_overrides_lock():
    # PRICING=30, ADDRESS=20 in J-One config.
    lock = IntentLock(lock_turns=2)
    state = {IntentLock.KEY_LOCKED: "PRICING", IntentLock.KEY_TURNS_LEFT: 2}
    effective = lock.apply(state, raw_intent="ADDRESS", intents=_intents())
    assert effective == "ADDRESS"
    assert state[IntentLock.KEY_LOCKED] == "ADDRESS"
    assert state[IntentLock.KEY_TURNS_LEFT] == 2


def test_lower_priority_does_not_override_lock():
    # ADDRESS=20, ROOMS=60 in J-One config.
    lock = IntentLock(lock_turns=2)
    state = {IntentLock.KEY_LOCKED: "ADDRESS", IntentLock.KEY_TURNS_LEFT: 2}
    effective = lock.apply(state, raw_intent="ROOMS", intents=_intents())
    assert effective == "ADDRESS"
    assert state[IntentLock.KEY_LOCKED] == "ADDRESS"
    assert state[IntentLock.KEY_TURNS_LEFT] == 1


def test_same_intent_repeated_does_not_reset_turns():
    lock = IntentLock(lock_turns=2)
    state = {IntentLock.KEY_LOCKED: "PRICING", IntentLock.KEY_TURNS_LEFT: 2}
    effective = lock.apply(state, raw_intent="PRICING", intents=_intents())
    assert effective == "PRICING"
    assert state[IntentLock.KEY_TURNS_LEFT] == 1


def test_state_is_mutated_in_place():
    lock = IntentLock(lock_turns=2)
    state: dict = {}
    lock.apply(state, raw_intent="GREETING", intents=_intents())
    assert IntentLock.KEY_LOCKED in state
    assert IntentLock.KEY_TURNS_LEFT in state

