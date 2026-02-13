from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.integrations.google_sheets import GoogleSheetsAdapter


@pytest.mark.asyncio
async def test_execute_append_lead_calls_append_lead():
    adapter = GoogleSheetsAdapter({})
    adapter.append_lead = AsyncMock(return_value={"success": True})  # type: ignore[method-assign]
    result = await adapter.execute("append_lead", {"message": "hi"})
    assert result == {"success": True}
    adapter.append_lead.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_unknown_returns_success_false():
    adapter = GoogleSheetsAdapter({})
    result = await adapter.execute("unknown", {})
    assert result["success"] is False


@pytest.mark.asyncio
async def test_append_lead_builds_row_from_params():
    adapter = GoogleSheetsAdapter({"spreadsheet_id": "s", "sheet_name": "Лиды"})
    adapter._append_row = AsyncMock(return_value={"success": True})  # type: ignore[method-assign]

    params = {
        "datetime": "2026-02-15T10:00:00Z",
        "channel": "telegram",
        "name": "Ivan",
        "contact": "+7999",
        "message": "Hello",
        "source": "AgentBox",
        "status": "new",
        "note": "n",
    }

    result = await adapter.append_lead(params)
    assert result == {"success": True}

    (row,), _kwargs = adapter._append_row.await_args.args, adapter._append_row.await_args.kwargs
    assert isinstance(row, list)
    assert len(row) == 8
    assert row[0] == "2026-02-15T10:00:00Z"
    assert row[1] == "telegram"
    assert row[2] == "Ivan"
    assert row[3] == "+7999"
    assert row[4] == "Hello"
    assert row[5] == "AgentBox"
    assert row[6] == "new"
    assert row[7] == "n"


@pytest.mark.asyncio
async def test_append_lead_without_service_account_path_returns_success_false():
    adapter = GoogleSheetsAdapter({"spreadsheet_id": "s"})
    result = await adapter.append_lead({"message": "hi"})
    assert result["success"] is False

