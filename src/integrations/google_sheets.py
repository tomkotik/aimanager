"""
Google Sheets Integration — log leads and bookings to a spreadsheet.
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.integrations.base import IntegrationAdapter

logger = logging.getLogger(__name__)


class GoogleSheetsAdapter(IntegrationAdapter):
    """
    Google Sheets integration for lead/booking logging.

    Config keys:
        service_account_path: str
        spreadsheet_id: str
        sheet_name: str — sheet tab name (default "Лиды")
    """

    integration_type = "google_sheets"

    def __init__(self, config: dict):
        super().__init__(config)
        self.spreadsheet_id = config.get("spreadsheet_id", "")
        self.sheet_name = config.get("sheet_name", "Лиды")

    async def execute(self, action: str, params: dict) -> dict:
        if action == "append_lead":
            return await self.append_lead(params)
        elif action == "append_booking":
            return await self.append_booking(params)
        return {"success": False, "error": f"Unknown action: {action}"}

    async def append_lead(self, params: dict) -> dict:
        """
        Append a lead row to the sheet.

        params: {
            "datetime": str,
            "channel": str,
            "name": str,
            "contact": str,
            "message": str,
            "source": str,
            "status": str,
            "note": str
        }
        """
        row = [
            params.get("datetime", datetime.utcnow().isoformat()),
            params.get("channel", ""),
            params.get("name", ""),
            params.get("contact", ""),
            params.get("message", ""),
            params.get("source", "AgentBox"),
            params.get("status", "new"),
            params.get("note", ""),
        ]
        return await self._append_row(row)

    async def append_booking(self, params: dict) -> dict:
        """Append a booking row."""
        row = [
            params.get("datetime", ""),
            params.get("hall", ""),
            params.get("client_name", ""),
            params.get("phone", ""),
            params.get("duration", ""),
            params.get("price", ""),
            params.get("status", "preliminary"),
        ]
        return await self._append_row(row)

    async def _append_row(self, row: list) -> dict:
        """Append a single row to the configured sheet."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            sa_path = self.config.get("service_account_path", "")
            if not sa_path:
                return {"success": False, "error": "No service account configured"}

            credentials = service_account.Credentials.from_service_account_file(
                sa_path,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            service = build("sheets", "v4", credentials=credentials)

            service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A1",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row]},
            ).execute()

            logger.info("Appended row to %s/%s", self.spreadsheet_id, self.sheet_name)
            return {"success": True}

        except Exception as e:
            logger.error("Failed to append to Sheets: %s", e)
            return {"success": False, "error": str(e)}

