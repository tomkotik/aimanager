from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.integrations.google_calendar import GoogleCalendarAdapter, _parse_ics_datetime


def test_parse_ics_datetime_utc():
    dt = _parse_ics_datetime("20260215T140000Z")
    assert dt == datetime(2026, 2, 15, 14, 0, 0, tzinfo=timezone.utc)


def test_parse_ics_events_parses_two_events():
    ics_text = (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\n"
        "DTSTART:20260215T140000Z\n"
        "DTEND:20260215T160000Z\n"
        "END:VEVENT\n"
        "BEGIN:VEVENT\n"
        "DTSTART:20260216T100000Z\n"
        "DTEND:20260216T110000Z\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    events = GoogleCalendarAdapter._parse_ics_events(ics_text)
    assert len(events) == 2
    assert events[0]["start"] == datetime(2026, 2, 15, 14, 0, 0, tzinfo=timezone.utc)
    assert events[0]["end"] == datetime(2026, 2, 15, 16, 0, 0, tzinfo=timezone.utc)
    assert events[1]["start"] == datetime(2026, 2, 16, 10, 0, 0, tzinfo=timezone.utc)
    assert events[1]["end"] == datetime(2026, 2, 16, 11, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_check_availability_slot_free_returns_available_true():
    ics_text = (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\n"
        "DTSTART:20260215T140000Z\n"
        "DTEND:20260215T160000Z\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    adapter = GoogleCalendarAdapter({"ics_url": "https://example.com/cal.ics"})
    response = httpx.Response(200, content=ics_text.encode("utf-8"))

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.check_availability(
            {"start": datetime(2026, 2, 15, 10, 0, 0, tzinfo=timezone.utc), "duration_hours": 2}
        )

    assert result == {"success": True, "available": True}


@pytest.mark.asyncio
async def test_check_availability_overlap_returns_available_false():
    ics_text = (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\n"
        "DTSTART:20260215T140000Z\n"
        "DTEND:20260215T160000Z\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    adapter = GoogleCalendarAdapter({"ics_url": "https://example.com/cal.ics"})
    response = httpx.Response(200, content=ics_text.encode("utf-8"))

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.check_availability(
            {"start": datetime(2026, 2, 15, 15, 0, 0, tzinfo=timezone.utc), "duration_hours": 2}
        )

    assert result == {"success": True, "available": False}


@pytest.mark.asyncio
async def test_check_availability_no_ics_url_fails_open_available_true():
    adapter = GoogleCalendarAdapter({"ics_url": ""})
    result = await adapter.check_availability({"start": datetime(2026, 2, 15, 10, 0, 0, tzinfo=timezone.utc)})
    assert result == {"success": True, "available": True}


@pytest.mark.asyncio
async def test_check_availability_http_error_fails_open_available_true():
    adapter = GoogleCalendarAdapter({"ics_url": "https://example.com/cal.ics"})

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=RuntimeError("HTTP error"))
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.check_availability(
            {"start": datetime(2026, 2, 15, 10, 0, 0, tzinfo=timezone.utc)}
        )

    assert result == {"success": True, "available": True}


@pytest.mark.asyncio
async def test_execute_check_availability_dispatches():
    adapter = GoogleCalendarAdapter({"ics_url": ""})
    adapter.check_availability = AsyncMock(return_value={"success": True, "available": True})  # type: ignore[method-assign]
    result = await adapter.execute("check_availability", {"start": "2026-02-15T10:00:00+00:00"})
    assert result == {"success": True, "available": True}
    adapter.check_availability.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_unknown_action_returns_error():
    adapter = GoogleCalendarAdapter({"ics_url": ""})
    result = await adapter.execute("unknown", {})
    assert result["success"] is False
    assert "Unknown action" in result["error"]

