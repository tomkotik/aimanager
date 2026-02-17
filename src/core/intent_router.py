"""
Intent Router — determines user intent by matching keywords from the config.

Usage:
    router = IntentRouter(intents)
    intent_id = router.detect("Сколько стоит съёмка?")
    # → "PRICING"
"""

from __future__ import annotations

from src.core.schemas import IntentConfig


class IntentRouter:
    """
    Detects user intent by matching marker phrases against the incoming text.

    Intents are checked in priority order (lower number = higher priority).
    The first matching intent is returned. If none match, returns the fallback.
    """

    DEFAULT_FALLBACK = "SAFE_FAQ"

    def __init__(self, intents: list[IntentConfig], fallback: str = DEFAULT_FALLBACK):
        # Sort intents by priority (ascending = highest priority first).
        self.intents = sorted(intents, key=lambda i: i.priority)
        self.fallback = fallback

    def detect(self, text: str) -> str:
        """Backward-compatible shortcut returning only intent id."""
        intent_id, _confidence = self.detect_with_confidence(text)
        return intent_id

    def detect_with_confidence(self, text: str) -> tuple[str, float]:
        """
        Detect intent and return a simple confidence score.

        Confidence is heuristic-based (marker overlap quality):
        - exact marker hit -> 0.95
        - fallback -> 0.25
        """
        lower = text.lower()
        for intent in self.intents:
            if self._matches(lower, intent.markers):
                return intent.id, 0.95
        return self.fallback, 0.25

    def get_intent_config(self, intent_id: str) -> IntentConfig | None:
        """Return the full IntentConfig for a given intent ID, or None."""
        for intent in self.intents:
            if intent.id == intent_id:
                return intent
        return None

    @staticmethod
    def _matches(text_lower: str, markers: list[str]) -> bool:
        """Check if any marker phrase is found in the text."""
        return any(marker.lower() in text_lower for marker in markers)

