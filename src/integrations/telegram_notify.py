from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from src.core.secrets import resolve_secret


@dataclass
class TelegramNotifier:
    """Lightweight Telegram sender for manager escalation alerts."""

    bot_token: str
    chat_id: str
    thread_id: int | None = None

    @classmethod
    def from_secrets(cls, tenant_slug: str) -> "TelegramNotifier | None":
        token = (
            resolve_secret(tenant_slug, "telegram_bot_token")
            or os.getenv("TELEGRAM_BOT_TOKEN")
            or ""
        ).strip()
        chat_id = (
            resolve_secret(tenant_slug, "escalation_chat_id")
            or resolve_secret(tenant_slug, "telegram_escalation_chat_id")
            or os.getenv("TELEGRAM_ESCALATION_CHAT_ID")
            or ""
        ).strip()
        thread_raw = (
            resolve_secret(tenant_slug, "escalation_thread_id")
            or os.getenv("TELEGRAM_ESCALATION_THREAD_ID")
            or ""
        ).strip()

        if not token or not chat_id:
            return None

        thread_id: int | None = None
        if thread_raw.isdigit():
            thread_id = int(thread_raw)

        return cls(bot_token=token, chat_id=chat_id, thread_id=thread_id)

    async def send_escalation(
        self,
        client_name: str | None,
        channel: str | None,
        last_message: str | None,
        conversation_link: str | None = None,
    ) -> dict:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        safe_client = (client_name or "Клиент").strip()
        safe_channel = (channel or "unknown").strip()
        safe_text = (last_message or "").strip()
        if len(safe_text) > 1200:
            safe_text = safe_text[:1200] + "…"

        lines = [
            "🔔 Эскалация лида",
            f"Клиент: {safe_client}",
            f"Канал: {safe_channel}",
        ]
        if safe_text:
            lines.append(f"Сообщение: {safe_text}")
        if conversation_link:
            base_url = os.getenv("AGENTBOX_DASHBOARD_URL", "").strip().rstrip("/")
            full_link = f"{base_url}{conversation_link}" if base_url and conversation_link.startswith("/") else conversation_link
            lines.append(f"Диалог: {full_link}")

        payload: dict = {
            "chat_id": self.chat_id,
            "text": "\n".join(lines),
            "disable_web_page_preview": True,
        }
        if self.thread_id is not None:
            payload["message_thread_id"] = self.thread_id

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()

            if resp.status_code == 200 and data.get("ok"):
                result = data.get("result") or {}
                return {"success": True, "message_id": result.get("message_id")}

            return {
                "success": False,
                "error": data.get("description") or f"telegram_http_{resp.status_code}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
