"""
Action Tag Parser — extracts and removes action tags from LLM output.

Supported tags:
  [ACTION:CREATE_BOOKING]   — create a calendar booking
  [ACTION:RESET]            — reset conversation state
  [ACTION:ESCALATE]         — hand off to human manager
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedActions:
    """Result of parsing action tags from text."""

    clean_text: str
    actions: list[str]

    @property
    def has_booking(self) -> bool:
        return "CREATE_BOOKING" in self.actions

    @property
    def has_reset(self) -> bool:
        return "RESET" in self.actions

    @property
    def has_escalate(self) -> bool:
        return "ESCALATE" in self.actions


_TAG_PATTERN = re.compile(r"\[ACTION:(\w+)\]")


def parse_action_tags(text: str) -> ParsedActions:
    """Extract all [ACTION:XXX] tags from text and return cleaned text + action list."""
    actions = _TAG_PATTERN.findall(text)
    clean = _TAG_PATTERN.sub("", text).strip()
    # Clean up whitespace left by removed tags.
    clean = re.sub(r"\n\s*\n", "\n\n", clean).strip()

    return ParsedActions(clean_text=clean, actions=actions)

