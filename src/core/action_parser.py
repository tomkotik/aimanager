"""
Action Tag Parser — extracts and removes action tags from LLM output.

Supported tags:
  [ACTION:CREATE_BOOKING]   — create a calendar booking
  [ACTION:RESET]            — reset conversation state
  [ACTION:ESCALATE]         — hand off to human manager
  [BOOKING:дата|время|длительность|зал|имя|телефон] — structured booking data
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedActions:
    """Result of parsing action tags from text."""

    clean_text: str
    actions: list[str]
    booking_data: dict | None = None

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
_BOOKING_PATTERN = re.compile(r"\[BOOKING:([^\]]+)\]")


def parse_action_tags(text: str) -> ParsedActions:
    """Extract all [ACTION:XXX] and [BOOKING:...] tags from text and return cleaned text + action list."""
    actions = _TAG_PATTERN.findall(text)
    booking_data = None
    
    # Parse booking tag if present
    booking_match = _BOOKING_PATTERN.search(text)
    if booking_match:
        booking_str = booking_match.group(1)
        booking_data = _parse_booking_data(booking_str)
        if booking_data:
            actions.append("CREATE_BOOKING")
    
    # Remove all tags from text
    clean = _TAG_PATTERN.sub("", text).strip()
    clean = _BOOKING_PATTERN.sub("", clean).strip()
    
    # Clean up whitespace left by removed tags
    clean = re.sub(r"\n\s*\n", "\n\n", clean).strip()

    return ParsedActions(clean_text=clean, actions=actions, booking_data=booking_data)


def _parse_booking_data(booking_str: str) -> dict | None:
    """
    Parse booking data from string format: дата|время|длительность|зал|имя|телефон
    
    Returns dict with keys: date, time, duration, room, name, phone
    """
    try:
        parts = [p.strip() for p in booking_str.split("|")]
        
        # Support both old format (5 fields) and new format (6 fields)
        if len(parts) == 5:
            # Old format без duration: дата|время|зал|имя|телефон
            return {
                "date": parts[0],
                "time": parts[1],
                "room": parts[2],
                "name": parts[3],
                "phone": parts[4],
            }
        elif len(parts) == 6:
            # New format с duration: дата|время|длительность|зал|имя|телефон
            return {
                "date": parts[0],
                "time": parts[1],
                "duration": parts[2],
                "room": parts[3],
                "name": parts[4],
                "phone": parts[5],
            }
        else:
            return None
            
    except Exception:
        return None
