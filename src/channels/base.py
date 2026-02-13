"""
Base Channel Adapter — abstract interface for messenger integrations.

To add a new channel:
1. Create a file in src/channels/ (e.g., telegram.py)
2. Subclass ChannelAdapter
3. Implement receive(), send(), get_lead_info()
4. Register in CHANNEL_REGISTRY
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from src.core.pipeline import IncomingMessage

logger = logging.getLogger(__name__)


class ChannelAdapter(ABC):
    """
    Base class for all channel adapters.

    Each adapter handles communication with one external messaging platform.
    """

    # Channel type identifier (e.g., "umnico", "telegram", "whatsapp").
    channel_type: str = ""

    def __init__(self, config: dict):
        """
        Args:
            config: Channel-specific configuration from agent.yaml channels[].config
        """
        self.config = config

    @abstractmethod
    async def receive(self) -> list[IncomingMessage]:
        """
        Fetch new incoming messages from the channel.

        For poll-based channels (Umnico): fetches unprocessed messages.
        For webhook-based channels (Telegram): not used (messages come via webhook).

        Returns:
            List of normalized IncomingMessage objects.
        """

    @abstractmethod
    async def send(self, channel_conversation_id: str, text: str) -> bool:
        """
        Send a message to the channel.

        Args:
            channel_conversation_id: External conversation/chat ID.
            text: Message text to send.

        Returns:
            True if sent successfully.
        """

    @abstractmethod
    async def get_lead_info(self, channel_conversation_id: str) -> dict:
        """
        Fetch lead/contact information from the channel.

        Returns:
            Dict with optional keys: name, phone, email, channel_url, etc.
        """

    async def setup(self) -> None:
        """Optional setup hook (e.g., register webhooks). Called on agent start."""

    async def teardown(self) -> None:
        """Optional cleanup hook. Called on agent stop."""


# --- Channel Registry ---

# Map of channel_type -> adapter class.
# Populated by register_channel() or by importing channel modules.
CHANNEL_REGISTRY: dict[str, type[ChannelAdapter]] = {}


def register_channel(channel_type: str):
    """Decorator to register a channel adapter class."""

    def decorator(cls: type[ChannelAdapter]):
        cls.channel_type = channel_type
        CHANNEL_REGISTRY[channel_type] = cls
        return cls

    return decorator


def get_channel_adapter(channel_type: str, config: dict) -> ChannelAdapter:
    """
    Factory: create a channel adapter by type.

    Args:
        channel_type: e.g., "umnico", "telegram"
        config: Channel-specific config dict.

    Returns:
        Instantiated ChannelAdapter.

    Raises:
        ValueError: If channel_type is not registered.
    """
    cls = CHANNEL_REGISTRY.get(channel_type)
    if cls is None:
        available = ", ".join(CHANNEL_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Unknown channel type: '{channel_type}'. Available: {available}")
    return cls(config)

