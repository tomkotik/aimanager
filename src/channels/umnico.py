"""
Umnico Channel Adapter — integrates with Umnico messenger aggregator API.

API Docs: https://api.umnico.com
Base URL: https://api.umnico.com/v1.3

Polling workflow:
1. GET /leads/inbox -> list of leads with latest messages
2. GET /messaging/{leadId}/sources -> list of messaging sources
3. POST /messaging/{leadId}/history/{sourceId} -> conversation history
4. POST /messaging/{leadId}/send -> send reply
"""

from __future__ import annotations

import logging

from src.channels.base import ChannelAdapter, register_channel
from src.core.pipeline import IncomingMessage

logger = logging.getLogger(__name__)

UMNICO_BASE_URL = "https://api.umnico.com/v1.3"


@register_channel("umnico")
class UmnicoAdapter(ChannelAdapter):
    """
    Umnico channel adapter (poll-based).

    Config keys:
        token_secret: str - name of the secret containing Umnico API token
        poll_interval_ms: int - polling interval in milliseconds (default 3000)

    Note: The actual token value is resolved at runtime by the worker/secret manager.
    For now, it can be passed directly in config["token"] for simplicity.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.token: str = config.get("token", "")
        self.base_url: str = config.get("base_url", UMNICO_BASE_URL)
        self._user_id: str | None = None

    async def receive(self) -> list[IncomingMessage]:
        """
        Fetch new incoming messages from Umnico inbox.

        Returns leads where the latest message is incoming (from customer).
        """
        import httpx

        messages: list[IncomingMessage] = []

        async with httpx.AsyncClient() as client:
            # 1. Get inbox leads.
            leads = await self._api_get(client, "/leads/inbox?limit=50&source_types=message")
            if not isinstance(leads, list):
                return messages

            for lead in leads:
                # Only process leads where last message is incoming.
                lead_msg = lead.get("message", {})
                if not lead_msg.get("incoming"):
                    continue

                lead_id = str(lead.get("id", ""))
                if not lead_id:
                    continue

                # 2. Get sources for this lead.
                sources = await self._api_get(client, f"/messaging/{lead_id}/sources")
                if not isinstance(sources, list):
                    continue

                for source in sources:
                    source_id = str(source.get("realId", source.get("id", "")))
                    if not source_id:
                        continue

                    # 3. Get message history.
                    history = await self._api_post(client, f"/messaging/{lead_id}/history/{source_id}", body={})
                    if not history or not isinstance(history.get("messages"), list):
                        continue

                    # Find latest incoming message.
                    incoming_msgs = [m for m in history["messages"] if m.get("incoming")]
                    if not incoming_msgs:
                        continue

                    incoming_msgs.sort(key=lambda m: m.get("datetime", 0))
                    last = incoming_msgs[-1]

                    text = (last.get("message", {}).get("text", "") or "").strip()
                    if not text:
                        continue

                    msg_id = str(last.get("messageId", f"{last.get('datetime', '')}-{len(text)}-in"))

                    messages.append(
                        IncomingMessage(
                            channel_type="umnico",
                            channel_conversation_id=f"{lead_id}:{source_id}",
                            channel_message_id=msg_id,
                            text=text,
                            sender_name=last.get("sender", {}).get("name"),
                            metadata={
                                "lead_id": lead_id,
                                "source_id": source_id,
                                "source_type": source.get("type", "message"),
                            },
                        )
                    )

        return messages

    async def send(self, channel_conversation_id: str, text: str) -> bool:
        """
        Send a reply to a Umnico lead.

        channel_conversation_id format: "{lead_id}:{source_id}"
        """
        import httpx

        parts = channel_conversation_id.split(":", 1)
        if len(parts) != 2:
            logger.error("Invalid Umnico conversation ID: %s", channel_conversation_id)
            return False

        lead_id, source_id = parts

        # Ensure we have the user_id (manager ID for sending).
        user_id = await self._ensure_user_id()

        body = {
            "message": {"text": text},
            "source": source_id,
            "userId": user_id,
        }

        async with httpx.AsyncClient() as client:
            result = await self._api_post(client, f"/messaging/{lead_id}/send", body=body)

        success = result is not None
        if success:
            logger.info("Sent message to Umnico lead %s", lead_id)
        else:
            logger.error("Failed to send message to Umnico lead %s", lead_id)

        return success

    async def get_lead_info(self, channel_conversation_id: str) -> dict:
        """Fetch lead/contact info from Umnico."""
        parts = channel_conversation_id.split(":", 1)
        if len(parts) != 2:
            return {}

        lead_id = parts[0]

        import httpx

        async with httpx.AsyncClient() as client:
            lead = await self._api_get(client, f"/leads/{lead_id}")

        if not lead:
            return {}

        customer = lead.get("customer", {})
        return {
            "name": customer.get("name"),
            "phone": customer.get("phone"),
            "email": customer.get("email"),
        }

    async def _ensure_user_id(self) -> str | None:
        """Get the manager user ID (cached)."""
        if self._user_id:
            return self._user_id

        import httpx

        async with httpx.AsyncClient() as client:
            managers = await self._api_get(client, "/managers")

        if isinstance(managers, list) and managers:
            self._user_id = str(managers[0].get("id", ""))

        return self._user_id

    async def _api_get(self, client, path: str):
        """Make authenticated GET request to Umnico API."""
        try:
            resp = await client.get(
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10.0,
            )
            if resp.status_code == 204:
                return None
            if not resp.is_success:
                logger.warning("Umnico API error: %s %s", resp.status_code, path)
                return None
            return resp.json()
        except Exception as e:
            logger.error("Umnico API request failed: %s", e)
            return None

    async def _api_post(self, client, path: str, body: dict):
        """Make authenticated POST request to Umnico API."""
        try:
            resp = await client.post(
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=10.0,
            )
            if resp.status_code == 204:
                return None
            if not resp.is_success:
                logger.warning("Umnico API error: %s %s", resp.status_code, path)
                return None
            return resp.json()
        except Exception as e:
            logger.error("Umnico API request failed: %s", e)
            return None

