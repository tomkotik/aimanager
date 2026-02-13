from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.telegram import TelegramAdapter
from src.core.pipeline import OutgoingMessage
from src.db import get_db
from src.main import app


def test_parse_webhook_text_message_returns_incoming_message():
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "text": "Hello",
            "chat": {"id": 123},
            "from": {
                "id": 7,
                "first_name": "John",
                "last_name": "Doe",
                "username": "jdoe",
            },
        },
    }

    incoming = TelegramAdapter.parse_webhook(payload)
    assert incoming is not None
    assert incoming.channel_type == "telegram"
    assert incoming.channel_conversation_id == "123"
    assert incoming.channel_message_id == "10"
    assert incoming.text == "Hello"
    assert incoming.sender_name == "John Doe"
    assert incoming.metadata["telegram_chat_id"] == 123
    assert incoming.metadata["telegram_user_id"] == 7
    assert incoming.metadata["telegram_username"] == "jdoe"


def test_parse_webhook_update_without_message_returns_none():
    assert TelegramAdapter.parse_webhook({}) is None


def test_parse_webhook_message_without_text_returns_none():
    payload = {"message": {"message_id": 1, "chat": {"id": 123}, "photo": [{"file_id": "x"}]}}
    assert TelegramAdapter.parse_webhook(payload) is None


def test_parse_webhook_sender_name_built_from_first_and_last_name():
    payload = {
        "message": {
            "message_id": 10,
            "text": "Hi",
            "chat": {"id": 1},
            "from": {"id": 1, "first_name": "Ivan", "last_name": "Petrov"},
        }
    }
    incoming = TelegramAdapter.parse_webhook(payload)
    assert incoming is not None
    assert incoming.sender_name == "Ivan Petrov"


@pytest.mark.asyncio
async def test_send_success_response_returns_true():
    adapter = TelegramAdapter({"token": "t"})
    response = httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        ok = await adapter.send("123", "hello")

    assert ok is True


@pytest.mark.asyncio
async def test_send_api_error_returns_false():
    adapter = TelegramAdapter({"token": "t"})
    response = httpx.Response(400, content=b"bad request")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        ok = await adapter.send("123", "hello")

    assert ok is False


@pytest.mark.asyncio
async def test_receive_returns_empty_list_for_webhook_based_channel():
    adapter = TelegramAdapter({"token": "t"})
    msgs = await adapter.receive()
    assert msgs == []


@pytest.mark.asyncio
async def test_webhook_endpoint_valid_payload_returns_ok_true():
    class _FakeResult:
        def __init__(self, row):
            self._row = row

        def first(self):
            return self._row

    class _FakeDb:
        async def execute(self, *_args, **_kwargs):
            return _FakeResult((_FakeAgent(), _FakeTenant()))

    class _FakeTenant:
        slug = "j-one-studio"

    class _FakeAgent:
        # Use any UUID-like string; only str(agent.id) is used.
        id = "00000000-0000-0000-0000-000000000000"
        config = {"channels": [{"type": "telegram", "config": {}}]}

    class _FakeConversation:
        id = "11111111-1111-1111-1111-111111111111"
        state = {}
        lead_name = None

    async def _override_get_db():
        yield _FakeDb()

    async def _fake_get_or_create_conversation(*_args, **_kwargs):
        return _FakeConversation(), True

    async def _fake_process(self, ctx):  # noqa: ANN001
        ctx.outgoing = OutgoingMessage(
            text="ok",
            conversation_id=ctx.incoming.metadata.get("conversation_id", ""),
            channel_conversation_id=ctx.incoming.channel_conversation_id,
            metadata={},
        )
        return ctx

    def _fake_resolve_secret(_tenant_slug: str, secret_name: str):
        if secret_name == "openai_key":
            return "sk-test"
        if secret_name == "telegram_bot_token":
            return "tg-test"
        return None

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with (
            patch("src.core.crud.get_or_create_conversation", new=_fake_get_or_create_conversation),
            patch("src.core.crud.get_conversation_history", new=AsyncMock(return_value=[])),
            patch("src.core.crud.save_message", new=AsyncMock(return_value=None)),
            patch("src.core.pipeline.MessagePipeline.process", new=_fake_process),
            patch("src.channels.telegram.TelegramAdapter.send", new=AsyncMock(return_value=True)),
            patch("src.api.v1.webhooks.resolve_secret", new=_fake_resolve_secret),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/webhooks/telegram/00000000-0000-0000-0000-000000000000",
                    json={
                        "message": {
                            "message_id": 1,
                            "text": "Hello",
                            "chat": {"id": 123},
                            "from": {"id": 7, "first_name": "John", "last_name": "Doe"},
                        }
                    },
                )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_webhook_endpoint_payload_without_message_returns_skipped_true():
    async def _override_get_db():
        yield AsyncMock(spec=AsyncSession)

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/webhooks/telegram/00000000-0000-0000-0000-000000000000",
                json={},
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "skipped": True}
    finally:
        app.dependency_overrides.pop(get_db, None)
