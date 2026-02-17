from src.core.state_contract import normalize_flow_state, validate_flow_state


def test_validate_happy_path_created() -> None:
    flow = {
        "stage": "finalize",
        "booking_status": "created",
        "booking_event_id": "evt_123",
        "booking_data": {"date": "20.02.2026", "time": "18:00", "room": "Лофт"},
    }
    assert validate_flow_state(flow) == []


def test_validate_rejects_invalid_status() -> None:
    flow = {"stage": "offer", "booking_status": "weird"}
    errs = validate_flow_state(flow)
    assert "invalid_booking_status:weird" in errs


def test_validate_rejects_event_id_non_created() -> None:
    flow = {
        "stage": "finalize",
        "booking_status": "busy",
        "booking_event_id": "evt_1",
        "booking_data": {"date": "20.02.2026", "time": "18:00", "room": "Лофт"},
        "booking_conflict": {"reason": "slot_busy"},
    }
    errs = validate_flow_state(flow)
    assert "event_id_requires_created_status" in errs


def test_normalize_sets_created_when_event_present() -> None:
    flow = {
        "stage": "offer",
        "booking_status": "busy",
        "booking_event_id": "evt_1",
        "booking_data": {"room": "Лофт"},
    }
    norm = normalize_flow_state(flow)
    assert norm["booking_status"] == "created"
    assert norm["stage"] == "finalize"


def test_normalize_initial_defaults() -> None:
    norm = normalize_flow_state(None)
    assert norm["stage"] == "qualify"
    assert norm["booking_status"] == ""
    assert norm["booking_data"] == {}
