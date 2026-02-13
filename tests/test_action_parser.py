from __future__ import annotations

from src.core.action_parser import parse_action_tags


def test_create_booking_only():
    parsed = parse_action_tags("[ACTION:CREATE_BOOKING]")
    assert parsed.actions == ["CREATE_BOOKING"]
    assert parsed.clean_text == ""


def test_tag_at_end():
    parsed = parse_action_tags("Бронь создана! [ACTION:CREATE_BOOKING]")
    assert parsed.actions == ["CREATE_BOOKING"]
    assert parsed.clean_text == "Бронь создана!"


def test_reset_then_text():
    parsed = parse_action_tags("[ACTION:RESET] Начнём сначала")
    assert parsed.actions == ["RESET"]
    assert parsed.clean_text == "Начнём сначала"


def test_multiple_tags():
    parsed = parse_action_tags("Текст [ACTION:CREATE_BOOKING] ещё [ACTION:ESCALATE]")
    assert parsed.actions == ["CREATE_BOOKING", "ESCALATE"]
    assert parsed.clean_text == "Текст  ещё"


def test_no_tags():
    parsed = parse_action_tags("Обычный текст без тегов")
    assert parsed.actions == []
    assert parsed.clean_text == "Обычный текст без тегов"


def test_has_properties():
    parsed = parse_action_tags("x [ACTION:CREATE_BOOKING] y [ACTION:RESET] z [ACTION:ESCALATE]")
    assert parsed.has_booking is True
    assert parsed.has_reset is True
    assert parsed.has_escalate is True

