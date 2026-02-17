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
          c.state->'flow'->>'booking_event_id' as booking_event_id,
          c.state->'flow'->>'booking_status' as booking_status,
          c.state->'flow'->>'stage' as stage,
          c.state->'flow'->'booking_data' as booking_data,
          c.state->'flow'->'booking_conflict' as booking_conflict,
          c.state->'flow'->>'manager_notified_busy' as manager_notified_busy,
          m.content as last_reply,
          m.metadata->'automation_trace' as automation_trace
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
    data = dict(row)
    # asyncpg JSONB is already parsed dict/list in most setups
    return data


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
    reply = trace[-1]["reply"] if trace else ""
    if not facts.get("booking_event_id"):
        return False, "booking_event_id is empty"
    if facts.get("booking_status") != "created":
        return False, f"booking_status={facts.get('booking_status')}"
    if not _contains(reply, "бронь подтвержд"):
        return False, "final reply is not confirmation"
    return True, "ok"


def check_busy_single(trace: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[bool, str]:
    reply = trace[-1]["reply"] if trace else ""
    if facts.get("booking_event_id"):
        return False, "booking_event_id must be empty for busy"
    if facts.get("booking_status") not in {"busy", "busy_escalated"}:
        return False, f"booking_status={facts.get('booking_status')}"
    if not _contains(reply, "занят"):
        return False, "reply does not state busy slot"
    return True, "ok"


def check_switch_room(trace: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[bool, str]:
    bd = facts.get("booking_data") or {}
    room = (bd.get("room") if isinstance(bd, dict) else None) or ""
    reply = trace[-1]["reply"] if trace else ""
    if room.lower() != "лофт":
        return False, f"final booking_data.room={room!r}, expected 'Лофт'"
    if not _contains(reply, "лофт"):
        return False, "final reply does not mention Лофт"
    return True, "ok"


def check_incomplete(trace: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[bool, str]:
    stage = facts.get("stage")
    if stage not in {"qualify", "offer", "close"}:
        return False, f"stage={stage}, expected non-final stage"
    return True, "ok"


def check_duplicate_after_created(trace: list[dict[str, Any]], facts: dict[str, Any]) -> tuple[bool, str]:
    if len(trace) < 2:
        return False, "need 2 turns"
    if not facts.get("booking_event_id"):
        return False, "booking_event_id missing"
    if not _contains(trace[1]["reply"], "бронь подтвержд"):
        return False, "second reply is not stable confirmation"
    return True, "ok"


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

    d1 = _future_date(120)
    d2 = _future_date(121)

    cases = [
        (
            "free_single",
            [
                f"Нужен зал Карелия {d1} в 11:00 на 2 часа, подкаст, 2 участника, имя РегрессФри, телефон 89990111{random.randint(100,999)}, подтверждаю бронь"
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
                f"Нужен зал Карелия {d2} в 12:00 на 2 часа, подкаст, имя РегрессДубль, телефон 89990111{random.randint(100,999)}, подтверждаю бронь",
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
