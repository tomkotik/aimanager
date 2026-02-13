from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.channels.umnico import UmnicoAdapter


@pytest.mark.asyncio
async def test_receive_returns_incoming_message():
    adapter = UmnicoAdapter({"token": "t"})
    adapter._api_get = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            # inbox leads
            [
                {"id": 1, "message": {"incoming": True}},
            ],
            # sources for lead 1
            [{"id": "s1", "realId": "rs1", "type": "message"}],
        ]
    )
    adapter._api_post = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "messages": [
                {"incoming": True, "datetime": 1, "message": {"text": "hi"}, "sender": {"name": "A"}},
                {
                    "incoming": True,
                    "datetime": 2,
                    "message": {"text": "Сколько стоит?"},
                    "sender": {"name": "Ivan"},
                    "messageId": "m2",
                },
            ]
        }
    )

    msgs = await adapter.receive()
    assert len(msgs) == 1
    m = msgs[0]
    assert m.channel_type == "umnico"
    assert m.channel_conversation_id == "1:rs1"
    assert m.channel_message_id == "m2"
    assert m.text == "Сколько стоит?"
    assert m.sender_name == "Ivan"
    assert m.metadata["lead_id"] == "1"
    assert m.metadata["source_id"] == "rs1"


@pytest.mark.asyncio
async def test_receive_skips_non_incoming_leads():
    adapter = UmnicoAdapter({"token": "t"})
    adapter._api_get = AsyncMock(return_value=[{"id": 1, "message": {"incoming": False}}])  # type: ignore[method-assign]
    msgs = await adapter.receive()
    assert msgs == []


@pytest.mark.asyncio
async def test_receive_empty_inbox_returns_empty_list():
    adapter = UmnicoAdapter({"token": "t"})
    adapter._api_get = AsyncMock(return_value=[])  # type: ignore[method-assign]
    msgs = await adapter.receive()
    assert msgs == []


@pytest.mark.asyncio
async def test_send_parses_conversation_id_and_calls_api():
    adapter = UmnicoAdapter({"token": "t"})
    adapter._ensure_user_id = AsyncMock(return_value="u1")  # type: ignore[method-assign]
    adapter._api_post = AsyncMock(return_value={"ok": True})  # type: ignore[method-assign]

    ok = await adapter.send("lead1:source1", "hello")
    assert ok is True
    assert adapter._api_post.await_count == 1
    _client, path = adapter._api_post.await_args.args[:2]
    assert "/messaging/lead1/send" in path


@pytest.mark.asyncio
async def test_send_invalid_conversation_id_returns_false():
    adapter = UmnicoAdapter({"token": "t"})
    ok = await adapter.send("bad", "hello")
    assert ok is False


@pytest.mark.asyncio
async def test_get_lead_info_returns_customer_fields():
    adapter = UmnicoAdapter({"token": "t"})
    adapter._api_get = AsyncMock(  # type: ignore[method-assign]
        return_value={"customer": {"name": "Ivan", "phone": "+7999", "email": "a@b.com"}}
    )
    info = await adapter.get_lead_info("1:s1")
    assert info["name"] == "Ivan"
    assert info["phone"] == "+7999"
    assert info["email"] == "a@b.com"


@pytest.mark.asyncio
async def test_api_error_handling_does_not_crash():
    adapter = UmnicoAdapter({"token": "t"})
    adapter._api_get = AsyncMock(return_value=None)  # type: ignore[method-assign]
    msgs = await adapter.receive()
    assert msgs == []

    adapter._ensure_user_id = AsyncMock(return_value="u1")  # type: ignore[method-assign]
    adapter._api_post = AsyncMock(return_value=None)  # type: ignore[method-assign]
    ok = await adapter.send("1:s1", "hello")
    assert ok is False

