from __future__ import annotations

"""State contract for transactional booking flows.

This module defines a small, explicit contract that can be reused by
pipeline/webhooks/tests to keep conversation state predictable.
"""

from typing import Any

STAGES = {"qualify", "offer", "close", "finalize"}
BOOKING_STATUSES = {"", "pending_manager", "busy", "busy_escalated", "created"}


def validate_flow_state(flow: dict[str, Any] | None) -> list[str]:
    """Return contract violations for flow-state.

    Empty list means contract is valid.
    """
    errs: list[str] = []
    f = flow or {}

    stage = str(f.get("stage") or "")
    if stage and stage not in STAGES:
        errs.append(f"invalid_stage:{stage}")

    status = str(f.get("booking_status") or "")
    if status not in BOOKING_STATUSES:
        errs.append(f"invalid_booking_status:{status}")

    bd = f.get("booking_data") or {}
    if bd and not isinstance(bd, dict):
        errs.append("booking_data_not_dict")

    conflict = f.get("booking_conflict") or {}
    if conflict and not isinstance(conflict, dict):
        errs.append("booking_conflict_not_dict")

    event_id = f.get("booking_event_id")
    if event_id and status and status != "created":
        errs.append("event_id_requires_created_status")

    # Basic shape checks when status is busy-ish.
    if status in {"busy", "busy_escalated"}:
        if not isinstance(conflict, dict) or not conflict.get("reason"):
            errs.append("busy_status_requires_conflict_reason")

    # Finalize stage must have core fields.
    if stage == "finalize":
        if not isinstance(bd, dict):
            errs.append("finalize_requires_booking_data")
        else:
            core = ["date", "time", "room"]
            missing = [k for k in core if not bd.get(k)]
            if missing and not event_id:
                errs.append(f"finalize_missing_core:{','.join(missing)}")

    return errs


def normalize_flow_state(flow: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize minimal contract invariants without changing business intent."""
    f = dict(flow or {})
    f.setdefault("stage", "qualify")

    status = str(f.get("booking_status") or "")
    event_id = f.get("booking_event_id")

    if event_id:
        f["booking_status"] = "created"
        f["stage"] = "finalize"
    elif status not in BOOKING_STATUSES:
        f["booking_status"] = ""

    if not isinstance(f.get("booking_data"), dict):
        f["booking_data"] = {}

    if f.get("booking_conflict") is not None and not isinstance(f.get("booking_conflict"), dict):
        f["booking_conflict"] = {}

    return f
