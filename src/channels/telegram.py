"""
Telegram Bot Channel Adapter — webhook-based integration.

Setup:
1. Create a bot via @BotFather -> get token
2. Set webhook: POST https://api.telegram.org/bot{token}/setWebhook?url={our_url}/api/v1/webhooks/telegram/{agent_id}
"""

from __future__ import annotations

import logging

from src.channels.base import ChannelAdapter, register_channel
from src.core.pipeline import IncomingMessage

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


@register_channel("telegram")
class TelegramAdapter(ChannelAdapter):
    """
    Telegram Bot API adapter (webhook-based).

    Config keys:
        token_secret: str - name of the secret containing bot token
        token: str - direct bot token (for dev/testing)
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.token: str = config.get("token", "")
        self.api_base: str = f"{TELEGRAM_API_BASE}{self.token}"

    async def receive(self) -> list[IncomingMessage]:
        """Not used for webhook-based channels. Messages arrive via webhook endpoint."""
        return []

    @staticmethod
    def parse_webhook(payload: dict) -> IncomingMessage | None:
        """
        Parse a Telegram webhook update into IncomingMessage.

        Args:
            payload: Raw Telegram Update object.

        Returns:
            IncomingMessage or None if the update is not a text message.
        """
        message = payload.get("message", {})
        text = message.get("text", "")
        if not text:
            return None

        chat = message.get("chat", {})
        from_user = message.get("from", {})

        return IncomingMessage(
            channel_type="telegram",
            channel_conversation_id=str(chat.get("id", "")),
            channel_message_id=str(message.get("message_id", "")),
            text=text,
            sender_name=_build_name(from_user),
            metadata={
                "telegram_chat_id": chat.get("id"),
                "telegram_user_id": from_user.get("id"),
                "telegram_username": from_user.get("username"),
            },
        )

    async def send(self, channel_conversation_id: str, text: str) -> bool:
        """Send a message via Telegram Bot API."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.api_base}/sendMessage",
                    json={
                        "chat_id": channel_conversation_id,
                        "text": text,
                    },
                    timeout=10.0,
                )
            if resp.is_success:
                logger.info("Sent Telegram message to chat %s", channel_conversation_id)
                return True
            logger.warning("Telegram API error: %s", resp.status_code)
            return False
        except Exception as e:
            logger.error("Telegram send failed: %s", e)
            return False

    async def get_lead_info(self, channel_conversation_id: str) -> dict:
        """Telegram doesn't provide phone/email via Bot API without explicit sharing."""
        return {}

    async def setup(self) -> None:
        """
        Register webhook with Telegram.

        Called when agent starts. Requires the webhook_url to be set in config.
        """
        webhook_url = self.config.get("webhook_url")
        if not webhook_url:
            logger.warning("Telegram webhook_url not configured — skipping webhook setup")
            return

        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.api_base}/setWebhook",
                json={"url": webhook_url},
                timeout=10.0,
            )

        if resp.is_success:
            logger.info("Telegram webhook set: %s", webhook_url)
        else:
            logger.error("Failed to set Telegram webhook: %s", resp.text)


def _build_name(from_user: dict) -> str | None:
    """Build display name from Telegram user object."""
    parts = [from_user.get("first_name", ""), from_user.get("last_name", "")]
    name = " ".join(p for p in parts if p).strip()
    return name or from_user.get("username") or None

