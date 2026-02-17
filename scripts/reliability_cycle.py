#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from reliability_report import build_report


def _iso_week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _format_markdown(report: dict, mode: str) -> str:
    kpi = report.get("kpi", {})
    counts = report.get("counts", {})

    lines = []
    lines.append(f"# Reliability {mode.title()} Report")
    lines.append("")
    lines.append(f"- Generated at (UTC): {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Window (hours): {report.get('window_hours')}")
    lines.append(f"- Since (UTC): {report.get('since_utc')}")
    lines.append("")
    lines.append("## KPI")
    lines.append(f"- Booking success rate: {kpi.get('booking_success_rate_pct')}")
    lines.append(f"- False confirmations: {kpi.get('false_confirmation_count')}")
    lines.append(f"- Busy precision: {kpi.get('busy_detection_precision_pct')}")
    lines.append(f"- p95 latency (ms): {kpi.get('p95_latency_ms')}")
    lines.append("")
    lines.append("## Outcome counts")
    lines.append(f"- created: {counts.get('created', 0)}")
    lines.append(f"- busy: {counts.get('busy', 0)}")
    lines.append(f"- busy_escalated: {counts.get('busy_escalated', 0)}")
    lines.append(f"- pending_manager: {counts.get('pending_manager', 0)}")
    lines.append("")

    # KPI targets snapshot
    lines.append("## KPI targets check")
    success = kpi.get("booking_success_rate_pct")
    false_conf = kpi.get("false_confirmation_count")
    busy_prec = kpi.get("busy_detection_precision_pct")
    p95 = kpi.get("p95_latency_ms")

    def mark(ok: bool | None) -> str:
        if ok is None:
            return "⚪"
        return "✅" if ok else "❌"

    lines.append(f"- {mark((success is not None) and (success >= 99))} Booking success ≥ 99% (current: {success})")
    lines.append(f"- {mark((false_conf is not None) and (false_conf == 0))} False-confirmation = 0 (current: {false_conf})")
    lines.append(f"- {mark((busy_prec is not None) and (busy_prec >= 99))} Busy precision ≥ 99% (current: {busy_prec})")
    lines.append(f"- {mark((p95 is not None) and (p95 < 3000))} p95 latency < 3000ms (current: {p95})")

    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Generate periodic reliability reports")
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--db-url", default="")
    parser.add_argument("--hours", type=int, default=0)
    parser.add_argument("--agent-id", default="")
    parser.add_argument("--out-dir", default="ops/reports")
    args = parser.parse_args()

    env = __import__("os").environ
    db_url = args.db_url or env.get("DATABASE_URL", "")
    agent_id = args.agent_id or env.get("AGENT_ID", "")
    if not db_url:
        print("ERROR: --db-url or DATABASE_URL required")
        return 1

    hours = args.hours
    if hours <= 0:
        hours = 24 if args.mode == "daily" else 24 * 7

    report = await build_report(db_url, hours, agent_id=(agent_id or None))

    out_base = Path(args.out_dir)
    day = datetime.now(timezone.utc)
    daily_dir = out_base / "daily"
    weekly_dir = out_base / "weekly"
    daily_dir.mkdir(parents=True, exist_ok=True)
    weekly_dir.mkdir(parents=True, exist_ok=True)

    stamp = day.strftime("%Y%m%d-%H%M%S")
    if args.mode == "daily":
        jpath = daily_dir / f"reliability-{stamp}.json"
        mpath = daily_dir / f"reliability-{stamp}.md"
    else:
        wk = _iso_week_key(day)
        jpath = weekly_dir / f"reliability-{wk}.json"
        mpath = weekly_dir / f"reliability-{wk}.md"

    jpath.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mpath.write_text(_format_markdown(report, args.mode), encoding="utf-8")

    print(json.dumps({"mode": args.mode, "json": str(jpath), "md": str(mpath)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
