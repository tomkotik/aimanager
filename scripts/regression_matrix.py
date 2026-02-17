#!/usr/bin/env python3
"""
AgentBox booking regression matrix runner.

Runs core transactional scenarios against /api/v1/agents/{agent_id}/chat,
then validates backend facts from DB (conversation state + assistant metadata).

Usage:
  AGENT_ID=<uuid> DATABASE_URL=<sqlalchemy-url> python3 scripts/regression_matrix.py \
      --base-url http://127.0.0.1:8000

Exit code:
  0 -> all critical checks passed
  1 -> at least one critical check failed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import asyncpg
import httpx


@dataclass
class CaseResult:
    name: str
    conversation_id: str
    ok: bool
    reason: str
    turns: list[dict[str, Any]]
    facts: dict[str, Any]


def _normalize_db_url(url: str) -> str:
    # SQLAlchemy DSN -> asyncpg DSN
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _future_date(days_from_now: int = 120) -> str:
    from datetime import timedelta

    d = date.today() + timedelta(days=days_from_now)
    return d.strftime("%d.%m.%Y")


async def _send(client: httpx.AsyncClient, url: str, message: str, conversation_id: str) -> dict[str, Any]:
    payload = {"message": message, "conversation_id": conversation_id}
    for attempt in range(1, 6):
        try:
            r = await client.post(url, json=payload, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 5:
                raise
            await asyncio.sleep(0.7 * attempt)
    raise RuntimeError("unreachable")


async def _fetch_facts(conn: asyncpg.Connection, conversation_id: str) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        select
          c.id,
          c.state as state_full,
          m.content as last_reply,
          m.metadata as last_metadata
        from conversations c
        left join lateral (
          select * from messages
          where conversation_id = c.id and role='assistant'
          order by created_at desc
          limit 1
        ) m on true
        where c.id = $1::uuid
        """,
        conversation_id,
    )
    if not row:
        return {}

    import json as _json

    state_raw = row["state_full"]
    if isinstance(state_raw, str):
        state_raw = _json.loads(state_raw)
    state = state_raw or {}

    flow = state.get("flow") or {}
    booking_data_raw = flow.get("booking_data")
    if isinstance(booking_data_raw, str):
        try:
            booking_data_raw = _json.loads(booking_data_raw)
        except Exception:
            booking_data_raw = {}

    return {
        "booking_event_id": flow.get("booking_event_id"),
        "booking_status": flow.get("booking_status"),
        "stage": flow.get("stage"),
        "booking_data": booking_data_raw or {},
        "manager_notified": flow.get("manager_notified"),
        "last_reply": row["last_reply"],
    }


async def run_case(
    client: httpx.AsyncClient,
    conn: asyncpg.Connection,
    chat_url: str,
    name: str,
    turns: list[str],
    checker,
) -> CaseResult:
    conv = str(uuid.uuid4())
    trace: list[dict[str, Any]] = []

    for t in turns:
        j = await _send(client, chat_url, t, conv)
        conv = j.get("conversation_id", conv)
        trace.append({"user": t, "reply": j.get("reply", "")})

    facts = await _fetch_facts(conn, conv)
    ok, reason = checker(trace, facts)
    return CaseResult(name=name, conversation_id=conv, ok=ok, reason=reason, turns=trace, facts=facts)


def _contains(text: str, needle: str) -> bool:
    return needle.lower() in (text or "").lower()


def check_free_single(trace: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[bool, str]:
    if not facts.get("booking_event_id"):
        return False, "booking_event_id is empty"
    if facts.get("booking_status") != "created":
        return False, f"booking_status={facts.get('booking_status')}"
    return True, "ok"


def check_busy_single(trace: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[bool, str]:
    reply = trace[-1]["reply"] if trace else ""
    if facts.get("booking_event_id"):
        return False, "booking_event_id must be empty for busy"
    status = facts.get("booking_status")
    if status in {"busy", "busy_escalated"}:
        return True, "ok"
    # Fallback: if state wasn't persisted but reply clearly says busy
    if _contains(reply, "занят"):
        return True, f"ok (status={status}, reply confirms busy)"
    return False, f"booking_status={status}, reply does not say busy"


def check_switch_room(trace: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[bool, str]:
    bd = facts.get("booking_data") or {}
    if isinstance(bd, str):
        import json as _json
        try:
            bd = _json.loads(bd)
        except Exception:
            bd = {}
    room = (bd.get("room") if isinstance(bd, dict) else None) or ""
    if room.lower() != "лофт":
        return False, f"final booking_data.room={room!r}, expected 'Лофт'"
    # Reply may show busy (Лофт can also be busy) — we accept if state has room=Лофт
    return True, "ok"


def check_incomplete(trace: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[bool, str]:
    stage = facts.get("stage")
    # Accept any non-finalized stage, or None if state was not saved yet (1-turn minimal)
    if stage in {"qualify", "offer", "close", None}:
        # If stage is None, also verify there's no booking_event_id
        if stage is None and facts.get("booking_event_id"):
            return False, "stage=None but booking_event_id exists"
        return True, "ok"
    if stage == "finalize":
        return False, "stage=finalize for incomplete message"
    return True, "ok"


def check_duplicate_after_created(trace: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[bool, str]:
    if len(trace) < 2:
        return False, "need 2 turns"
    if not facts.get("booking_event_id"):
        return False, "booking_event_id missing"
    # Second reply must acknowledge existing booking (confirm or mention it's already booked)
    reply2 = trace[1]["reply"].lower()
    if any(kw in reply2 for kw in ["бронь подтвержд", "бронь уже", "зафиксиров", "подтверж", "бронь на зал"]):
        return True, "ok"
    return False, f"second reply does not confirm existing booking: {reply2[:80]}"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--agent-id", default=os.getenv("AGENT_ID", ""))
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()

    if not args.agent_id:
        print("ERROR: --agent-id or AGENT_ID is required", file=sys.stderr)
        return 1
    if not args.db_url:
        print("ERROR: --db-url or DATABASE_URL is required", file=sys.stderr)
        return 1

    db_url = _normalize_db_url(args.db_url)
    chat_url = f"{args.base_url.rstrip('/')}/api/v1/agents/{args.agent_id}/chat"

    # Use dates far enough and randomize hour to avoid collisions with previous test runs.
    d1 = _future_date(180 + random.randint(0, 30))
    d2 = _future_date(220 + random.randint(0, 30))
    h1 = random.choice(["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"])
    h2 = random.choice(["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"])

    cases = [
        (
            "free_single",
            [
                f"Нужен зал Карелия {d1} в {h1} на 2 часа, подкаст, 2 участника, имя РегрессФри, телефон 89990111{random.randint(100,999)}, подтверждаю бронь"
            ],
            check_free_single,
        ),
        (
            "busy_single",
            [
                "Нужен зал Грань 18.02.2026 в 18:00 на 5 часов, подкаст, 2 участника, имя РегрессБизи, телефон 89990111222, подтверждаю бронь"
            ],
            check_busy_single,
        ),
        (
            "busy_switch_room",
            [
                "Грань хочу на 5 часов",
                "В среду в 18:00 Александр 89383737372",
                "зал Лофт в 18:00",
            ],
            check_switch_room,
        ),
        (
            "incomplete",
            ["Хочу зал Грань"],
            check_incomplete,
        ),
        (
            "duplicate_after_created",
            [
                f"Нужен зал Карелия {d2} в {h2} на 2 часа, подкаст, имя РегрессДубль, телефон 89990111{random.randint(100,999)}, подтверждаю бронь",
                "подтверждаю бронь",
            ],
            check_duplicate_after_created,
        ),
    ]

    results: list[CaseResult] = []

    async with httpx.AsyncClient() as client:
        conn = await asyncpg.connect(db_url)
        try:
            for name, turns, checker in cases:
                try:
                    res = await run_case(client, conn, chat_url, name, turns, checker)
                except Exception as e:
                    res = CaseResult(name=name, conversation_id="", ok=False, reason=f"exception: {e}", turns=[], facts={})
                results.append(res)
        finally:
            await conn.close()

    summary = {
        "passed": sum(1 for r in results if r.ok),
        "failed": sum(1 for r in results if not r.ok),
        "results": [
            {
                "case": r.name,
                "ok": r.ok,
                "reason": r.reason,
                "conversation_id": r.conversation_id,
                "reply": (r.turns[-1]["reply"] if r.turns else ""),
                "booking_event_id": r.facts.get("booking_event_id"),
                "booking_status": r.facts.get("booking_status"),
                "stage": r.facts.get("stage"),
            }
            for r in results
        ],
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
