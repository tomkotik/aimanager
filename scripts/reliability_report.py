#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

import asyncpg


def _normalize_db_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def build_report(db_url: str, hours: int, agent_id: str | None = None) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    conn = await asyncpg.connect(_normalize_db_url(db_url))
    try:
        # Flow outcomes from conversation state
        rows = await conn.fetch(
            """
            select
              coalesce(state->'flow'->>'booking_status', '') as booking_status,
              count(*)::int as cnt
            from conversations c
            where c.updated_at >= $1
              and ($2::uuid is null or c.agent_id = $2::uuid)
            group by 1
            """,
            since,
            agent_id,
        )
        counts = {r["booking_status"]: r["cnt"] for r in rows}

        created = counts.get("created", 0)
        busy = counts.get("busy", 0)
        busy_escalated = counts.get("busy_escalated", 0)
        pending = counts.get("pending_manager", 0)

        denom = created + busy + busy_escalated
        booking_success_rate = round((created / denom) * 100, 2) if denom > 0 else None

        # False confirmation proxy: confirmation wording without booking_event_id in assistant metadata.
        false_confirm = await conn.fetchval(
            """
            select count(*)::int
            from messages m
            join conversations c on c.id = m.conversation_id
            where m.role='assistant'
              and m.created_at >= $1
              and ($2::uuid is null or c.agent_id = $2::uuid)
              and (
                    lower(m.content) like '%бронь подтвержд%'
                 or lower(m.content) like '%бронирование подтвержд%'
                 or lower(m.content) like '%ваша бронь%'
              )
              and coalesce(m.metadata->>'booking_event_id','') = ''
            """,
            since,
            agent_id,
        )

        # p95 latency from assistant metadata.latency_ms
        p95_latency = await conn.fetchval(
            """
            select percentile_cont(0.95) within group (
                order by (m.metadata->>'latency_ms')::numeric
            )
            from messages m
            join conversations c on c.id = m.conversation_id
            where m.role='assistant'
              and m.created_at >= $1
              and ($2::uuid is null or c.agent_id = $2::uuid)
              and coalesce(m.metadata->>'latency_ms','') ~ '^[0-9]+(\\.[0-9]+)?$'
            """,
            since,
            agent_id,
        )

        # Busy precision proxy: busy replies that have busy status in flow-state.
        busy_reply_total = await conn.fetchval(
            """
            select count(*)::int
            from messages m
            join conversations c on c.id = m.conversation_id
            where m.role='assistant'
              and m.created_at >= $1
              and ($2::uuid is null or c.agent_id = $2::uuid)
              and lower(m.content) like '%слот%занят%'
            """,
            since,
            agent_id,
        )
        busy_reply_with_busy_state = await conn.fetchval(
            """
            select count(*)::int
            from messages m
            join conversations c on c.id = m.conversation_id
            where m.role='assistant'
              and m.created_at >= $1
              and ($2::uuid is null or c.agent_id = $2::uuid)
              and lower(m.content) like '%слот%занят%'
              and coalesce(c.state->'flow'->>'booking_status','') in ('busy','busy_escalated')
            """,
            since,
            agent_id,
        )
        busy_precision = (
            round((busy_reply_with_busy_state / busy_reply_total) * 100, 2)
            if busy_reply_total > 0
            else None
        )

        return {
            "window_hours": hours,
            "agent_id": agent_id,
            "since_utc": since.isoformat(),
            "counts": {
                "created": created,
                "busy": busy,
                "busy_escalated": busy_escalated,
                "pending_manager": pending,
            },
            "kpi": {
                "booking_success_rate_pct": booking_success_rate,
                "false_confirmation_count": int(false_confirm or 0),
                "busy_detection_precision_pct": busy_precision,
                "p95_latency_ms": float(p95_latency) if p95_latency is not None else None,
            },
        }
    finally:
        await conn.close()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--agent-id", default=os.getenv("AGENT_ID", ""))
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    if not args.db_url:
        print("ERROR: --db-url or DATABASE_URL is required")
        return 1

    report = await build_report(args.db_url, args.hours, agent_id=(args.agent_id or None))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
