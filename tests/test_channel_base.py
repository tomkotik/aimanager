from __future__ import annotations

import pytest

from src.channels.base import CHANNEL_REGISTRY, ChannelAdapter, get_channel_adapter, register_channel
from src.core.pipeline import IncomingMessage


def test_register_channel_registers_class():
    CHANNEL_REGISTRY.clear()

    @register_channel("test")
    class TestAdapter(ChannelAdapter):
        async def receive(self) -> list[IncomingMessage]:
            return []

        async def send(self, channel_conversation_id: str, text: str) -> bool:
            return True

        async def get_lead_info(self, channel_conversation_id: str) -> dict:
            return {}

    assert "test" in CHANNEL_REGISTRY
    assert CHANNEL_REGISTRY["test"] is TestAdapter
    assert TestAdapter.channel_type == "test"


def test_get_channel_adapter_returns_instance():
    CHANNEL_REGISTRY.clear()

    @register_channel("test2")
    class Test2Adapter(ChannelAdapter):
        async def receive(self) -> list[IncomingMessage]:
            return []

        async def send(self, channel_conversation_id: str, text: str) -> bool:
            return True

        async def get_lead_info(self, channel_conversation_id: str) -> dict:
            return {}

    adapter = get_channel_adapter("test2", {"k": "v"})
    assert isinstance(adapter, Test2Adapter)
    assert adapter.config == {"k": "v"}


def test_get_channel_adapter_unknown_type_raises():
    CHANNEL_REGISTRY.clear()
    with pytest.raises(ValueError):
        get_channel_adapter("unknown", {})


def test_channel_adapter_is_abstract():
    with pytest.raises(TypeError):
        ChannelAdapter({})

