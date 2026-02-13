"""
Intent Lock — prevents intent flickering by locking the intent for N turns.

When a new intent is detected, it's locked for `lock_turns` (default 2) turns.
During the lock period, the locked intent is returned regardless of what the
router detects, unless a higher-priority marker explicitly overrides it.

State is stored in the conversation state dict (persisted in DB).
"""

from __future__ import annotations

from src.core.schemas import IntentConfig


class IntentLock:
    """
    Manages intent locking to prevent topic jumping.

    Usage:
        lock = IntentLock(lock_turns=2)
        effective_intent = lock.apply(state, raw_intent="GREETING", intents=intents)
    """

    # State keys stored in conversation.state dict.
    KEY_LOCKED = "locked_intent"
    KEY_TURNS_LEFT = "intent_lock_turns_left"

    def __init__(self, lock_turns: int = 2):
        self.lock_turns = lock_turns

    def apply(
        self,
        state: dict,
        raw_intent: str,
        intents: list[IntentConfig] | None = None,
    ) -> str:
        """
        Apply intent locking logic.

        Args:
            state: Mutable conversation state dict (will be modified in-place).
            raw_intent: The intent detected by IntentRouter for the current message.
            intents: Full list of intents (used to check priority for override).

        Returns:
            The effective intent to use for this turn.
        """
        locked = state.get(self.KEY_LOCKED)
        turns_left = state.get(self.KEY_TURNS_LEFT, 0)

        # If we have an active lock and the raw intent is the same -> just decrement.
        if locked and turns_left > 0 and raw_intent == locked:
            state[self.KEY_TURNS_LEFT] = turns_left - 1
            return locked

        # If lock is active but raw intent is different -> check for override.
        if locked and turns_left > 0 and raw_intent != locked:
            if self._should_override(raw_intent, locked, intents):
                # Higher-priority intent breaks the lock.
                state[self.KEY_LOCKED] = raw_intent
                state[self.KEY_TURNS_LEFT] = self.lock_turns
                return raw_intent
            # Lock holds: keep the locked intent.
            state[self.KEY_TURNS_LEFT] = turns_left - 1
            return locked

        # No active lock (or lock expired) -> set new lock.
        if raw_intent != locked:
            state[self.KEY_LOCKED] = raw_intent
            state[self.KEY_TURNS_LEFT] = self.lock_turns
        else:
            state[self.KEY_TURNS_LEFT] = 0

        return raw_intent

    @staticmethod
    def _should_override(
        new_intent: str,
        locked_intent: str,
        intents: list[IntentConfig] | None,
    ) -> bool:
        """
        Check if new_intent has higher priority (lower number) than locked_intent.
        ESCALATE always overrides. Unknown intents don't override.
        """
        if new_intent == "ESCALATE":
            return True

        if not intents:
            return False

        priority_map = {i.id: i.priority for i in intents}
        new_prio = priority_map.get(new_intent, 999)
        locked_prio = priority_map.get(locked_intent, 999)

        return new_prio < locked_prio

