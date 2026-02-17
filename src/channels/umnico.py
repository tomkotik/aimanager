"""
Umnico Channel Adapter — webhook-based integration via Umnico API v1.3.

Flow:
1. Agent saves `umnico_api_token` in secrets.
2. On setup(), adapter registers a webhook in Umnico pointing at our endpoint.
3. Incoming messages arrive as webhook events (type: "message.incoming").
4. Replies are sent via POST /v1.3/messaging/{leadId}/send.

Docs: https://api.umnico.com/docs/ru/
"""

from __future__ import annotations

import logging
from typing import Any

from src.channels.base import ChannelAdapter, register_channel
from src.core.pipeline import IncomingMessage

logger = logging.getLogger(__name__)

UMNICO_API_BASE = "https://api.umnico.com/v1.3"


@register_channel("umnico")
class UmnicoAdapter(ChannelAdapter):
    """
    Umnico API v1.3 adapter (webhook-based).

    Config keys:
        api_token: str — Umnico API bearer token (or resolved from secrets).
        webhook_url: str — public URL where Umnico should send events.
        webhook_name: str — human-readable name for the webhook (optional).
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_token: str = config.get("api_token", "")
        self.webhook_url: str = config.get("webhook_url", "")
        self.webhook_name: str = config.get("webhook_name", "AgentBOX")
        self.user_id: int | None = config.get("user_id")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def receive(self) -> list[IncomingMessage]:
        """Not used for webhook-based channels."""
        return []

    @staticmethod
    def parse_webhook(payload: dict) -> IncomingMessage | None:
        """
        Parse an Umnico webhook event into IncomingMessage.

        We only handle 'message.incoming' events with text content.

        Umnico payload structure:
        {
            "type": "message.incoming",
            "accountId": 147517,
            "leadId": 123,
            "isNewLead": true/false,
            "isNewCustomer": true/false,
            "message": {
                "datetime": 1564564311000,  // unix ms
                "incoming": true,
                "message": {"text": "...", "attachments": [...]},
                "sender": {"id": ..., "login": "...", "customerId": ...},
                "source": {"id": "...", "realId": 255, "saId": 88, ...},
                "messageId": "..."
            }
        }
        """
        event_type = payload.get("type", "")
        if event_type != "message.incoming":
            logger.debug("Umnico webhook: skipping event type=%s", event_type)
            return None

        msg_obj = payload.get("message", {})
        message_data = msg_obj.get("message", {})
        text = message_data.get("text", "")
        if not text:
            logger.debug("Umnico webhook: empty text, skipping")
            return None

        lead_id = payload.get("leadId")
        sender = msg_obj.get("sender", {})
        source = msg_obj.get("source", {})

        # Build a stable conversation ID from leadId (one lead = one conversation).
        channel_conversation_id = str(lead_id) if lead_id else ""

        sender_name = (
            sender.get("login")
            or sender.get("name")
            or None
        )

        return IncomingMessage(
            channel_type="umnico",
            channel_conversation_id=channel_conversation_id,
            channel_message_id=str(msg_obj.get("messageId", "")),
            text=text,
            sender_name=sender_name,
            metadata={
                "umnico_lead_id": lead_id,
                "umnico_account_id": payload.get("accountId"),
                "umnico_is_new_lead": payload.get("isNewLead", False),
                "umnico_is_new_customer": payload.get("isNewCustomer", False),
                "umnico_sender_id": sender.get("id"),
                "umnico_customer_id": sender.get("customerId"),
                "umnico_source_id": source.get("id"),
                "umnico_source_real_id": source.get("realId"),
                "umnico_sa_id": source.get("saId"),
                "umnico_source_type": source.get("type"),
                "umnico_sender_type": sender.get("type"),
            },
        )

    async def send(self, channel_conversation_id: str, text: str) -> bool:
        """
        Send a reply to an Umnico lead.

        channel_conversation_id is the Umnico leadId.
        """
        import httpx

        lead_id = channel_conversation_id

        try:
            # First, get the available sources for this lead to find the right channel.
            async with httpx.AsyncClient(timeout=15.0) as client:
                sources_resp = await client.get(
                    f"{UMNICO_API_BASE}/messaging/{lead_id}/sources",
                    headers=self._headers(),
                )

            if not sources_resp.is_success:
                logger.error(
                    "Umnico sources error for lead %s: %s %s",
                    lead_id, sources_resp.status_code, sources_resp.text,
                )
                return False

            sources = sources_resp.json()
            if not sources:
                logger.error("Umnico: no sources found for lead %s", lead_id)
                return False

            # Use the first message-type source, or fall back to the first one.
            source = next(
                (s for s in sources if s.get("type") == "message"),
                sources[0],
            )
            source_real_id = source.get("realId") or source.get("id")

            # Umnico requires userId for /messaging/{leadId}/send.
            user_id = await self._resolve_user_id()
            if not user_id:
                logger.error("Umnico send failed: cannot resolve userId")
                return False

            payload = {
                "message": {"text": text},
                "source": str(source_real_id),
                "userId": int(user_id),
            }

            # Include saId when available for stricter routing.
            if source.get("saId") is not None:
                payload["saId"] = source.get("saId")

            async with httpx.AsyncClient(timeout=15.0) as client:
                send_resp = await client.post(
                    f"{UMNICO_API_BASE}/messaging/{lead_id}/send",
                    headers=self._headers(),
                    json=payload,
                )

            if send_resp.is_success:
                logger.info(
                    "Sent Umnico message to lead %s via source %s userId=%s",
                    lead_id, source_real_id, user_id,
                )
                return True

            logger.warning(
                "Umnico send error: %s %s",
                send_resp.status_code, send_resp.text,
            )
            return False

        except Exception as e:
            logger.error("Umnico send failed: %s", e)
            return False

    async def _resolve_user_id(self) -> int | None:
        """Resolve Umnico manager userId (required by send endpoint)."""
        if self.user_id:
            return int(self.user_id)

        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{UMNICO_API_BASE}/managers", headers=self._headers())
            if not resp.is_success:
                logger.error("Umnico managers error: %s %s", resp.status_code, resp.text)
                return None

            managers = resp.json() or []
            if not managers:
                return None

            owner = next((m for m in managers if m.get("role") == "owner"), None)
            manager = owner or managers[0]
            uid = manager.get("id")
            if uid is not None:
                self.user_id = int(uid)
                return self.user_id
            return None
        except Exception as e:
            logger.error("Umnico _resolve_user_id failed: %s", e)
            return None

    async def get_lead_info(self, channel_conversation_id: str) -> dict:
        """Fetch lead/customer info from Umnico."""
        import httpx

        lead_id = channel_conversation_id
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{UMNICO_API_BASE}/leads/{lead_id}",
                    headers=self._headers(),
                )
            if not resp.is_success:
                return {}

            data = resp.json()
            customer = data.get("customer", {}) or {}
            return {
                "name": customer.get("name") or customer.get("login"),
                "phone": customer.get("phone"),
                "email": customer.get("email"),
                "umnico_lead_id": data.get("id"),
                "umnico_customer_id": data.get("customerId"),
            }
        except Exception as e:
            logger.error("Umnico get_lead_info failed: %s", e)
            return {}

    async def setup(self) -> None:
        """
        Register webhook in Umnico to receive events.

        Idempotent: checks existing webhooks first, updates if URL changed.
        """
        if not self.api_token or not self.webhook_url:
            logger.warning("Umnico adapter: api_token or webhook_url not configured, skipping setup")
            return

        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Get existing webhooks.
                resp = await client.get(
                    f"{UMNICO_API_BASE}/webhooks",
                    headers=self._headers(),
                )
                existing = resp.json() if resp.is_success else []

                # Check if our webhook already registered.
                our_hook = next(
                    (h for h in existing if h.get("url") == self.webhook_url),
                    None,
                )

                if our_hook:
                    hook_id = our_hook["id"]
                    if our_hook.get("status") != 1:
                        # Re-enable it.
                        await client.put(
                            f"{UMNICO_API_BASE}/webhooks/{hook_id}",
                            headers=self._headers(),
                            json={"status": 1},
                        )
                        logger.info("Umnico webhook re-enabled: id=%s", hook_id)
                    else:
                        logger.info("Umnico webhook already registered: id=%s url=%s", hook_id, self.webhook_url)
                else:
                    # Register new webhook.
                    create_resp = await client.post(
                        f"{UMNICO_API_BASE}/webhooks",
                        headers=self._headers(),
                        json={
                            "url": self.webhook_url,
                            "name": self.webhook_name,
                        },
                    )
                    if create_resp.is_success:
                        hook = create_resp.json()
                        logger.info("Umnico webhook created: id=%s url=%s", hook.get("id"), self.webhook_url)
                    else:
                        logger.error("Failed to create Umnico webhook: %s %s", create_resp.status_code, create_resp.text)

        except Exception as e:
            logger.error("Umnico webhook setup failed: %s", e)
