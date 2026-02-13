"""
Google Calendar Integration — check availability and create bookings.

Uses Google Calendar API via service account.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.integrations.base import IntegrationAdapter

logger = logging.getLogger(__name__)


class GoogleCalendarAdapter(IntegrationAdapter):
    """
    Google Calendar integration.

    Config keys:
        service_account_path: str — path to service account JSON file
        calendar_id: str — Google Calendar ID
        ics_url: str — public ICS URL (for read-only availability checks)
        default_duration_hours: int — default booking duration (default 2)
    """

    integration_type = "google_calendar"

    def __init__(self, config: dict):
        super().__init__(config)
        self.calendar_id = config.get("calendar_id", "")
        self.ics_url = config.get("ics_url", "")
        self.default_duration = config.get("default_duration_hours", 2)

    async def execute(self, action: str, params: dict) -> dict:
        """
        Dispatch to the appropriate calendar action.

        Actions:
            check_availability: params = {"start": datetime}
            create_booking: params = {"start": datetime, "end": datetime, "summary": str, "description": str}
        """
        if action == "check_availability":
            return await self.check_availability(params)
        elif action == "create_booking":
            return await self.create_booking(params)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    async def check_availability(self, params: dict) -> dict:
        """
        Check if a time slot is available by fetching the ICS feed.

        Args:
            params: {"start": datetime, "duration_hours": int (optional)}

        Returns:
            {"success": True, "available": bool}
        """
        if not self.ics_url:
            logger.warning("No ICS URL configured — assuming slot is free")
            return {"success": True, "available": True}

        import httpx

        try:
            start = params["start"]
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            duration = params.get("duration_hours", self.default_duration)
            end = start + timedelta(hours=duration)

            async with httpx.AsyncClient() as client:
                resp = await client.get(self.ics_url, timeout=10.0)
                ics_text = resp.text

            events = self._parse_ics_events(ics_text)

            overlaps = [
                e
                for e in events
                if e.get("start") and e.get("end") and start < e["end"] and end > e["start"]
            ]

            available = len(overlaps) == 0
            return {"success": True, "available": available}

        except Exception as e:
            logger.error("Calendar availability check failed: %s", e)
            # Fail open: assume free.
            return {"success": True, "available": True}

    async def create_booking(self, params: dict) -> dict:
        """
        Create a booking event in Google Calendar.

        Args:
            params: {
                "start": datetime,
                "end": datetime,
                "summary": str,
                "description": str (optional)
            }

        Returns:
            {"success": True, "event_id": str} or {"success": False, "error": str}
        """
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            sa_path = self.config.get("service_account_path", "")
            if not sa_path:
                return {"success": False, "error": "No service account configured"}

            credentials = service_account.Credentials.from_service_account_file(
                sa_path,
                scopes=["https://www.googleapis.com/auth/calendar"],
            )
            service = build("calendar", "v3", credentials=credentials)

            start = params["start"]
            end = params["end"]
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            if isinstance(end, str):
                end = datetime.fromisoformat(end)

            event = {
                "summary": params.get("summary", "Booking"),
                "description": params.get("description", ""),
                "start": {"dateTime": start.isoformat()},
                "end": {"dateTime": end.isoformat()},
            }

            result = service.events().insert(
                calendarId=self.calendar_id,
                body=event,
            ).execute()

            logger.info("Created calendar event: %s", result.get("id"))
            return {"success": True, "event_id": result.get("id", "")}

        except Exception as e:
            logger.error("Failed to create booking: %s", e)
            return {"success": False, "error": str(e)}

    @staticmethod
    def _parse_ics_events(ics_text: str) -> list[dict]:
        """Parse ICS text into a list of events with start/end datetimes."""
        events: list[dict] = []
        lines = ics_text.split("\n")
        in_event = False
        event: dict = {}

        for line in lines:
            line = line.strip()
            if line == "BEGIN:VEVENT":
                in_event = True
                event = {}
            elif line == "END:VEVENT":
                in_event = False
                events.append(event)
            elif in_event:
                if line.startswith("DTSTART"):
                    event["start"] = _parse_ics_datetime(line.split(":", 1)[-1])
                elif line.startswith("DTEND"):
                    event["end"] = _parse_ics_datetime(line.split(":", 1)[-1])

        return events


def _parse_ics_datetime(s: str) -> datetime | None:
    """Parse ICS datetime string (YYYYMMDDTHHMMSSZ)."""
    try:
        s = s.strip()
        y = int(s[0:4])
        m = int(s[4:6])
        d = int(s[6:8])
        h = int(s[9:11])
        mi = int(s[11:13])
        sec = int(s[13:15])
        if s.endswith("Z"):
            from datetime import timezone

            return datetime(y, m, d, h, mi, sec, tzinfo=timezone.utc)
        return datetime(y, m, d, h, mi, sec)
    except (ValueError, IndexError):
        return None

