"""
Golden test runner — loads YAML test cases and validates intent detection + postprocessing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.config_loader import load_tenant_config
from src.core.intent_router import IntentRouter
from src.core.postprocess import Postprocessor


GOLDEN_DIR = Path("tests/golden/j-one")


def _load_golden(filename: str) -> dict:
    with open(GOLDEN_DIR / filename, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def jone_router() -> IntentRouter:
    cfg = load_tenant_config("tenants/j-one-studio")
    return IntentRouter(cfg.dialogue_policy.intents)


@pytest.fixture
def jone_postprocessor() -> Postprocessor:
    cfg = load_tenant_config("tenants/j-one-studio")
    return Postprocessor(cfg.agent.style)


_intent_files = ["greeting.yaml", "pricing.yaml", "address.yaml", "booking.yaml", "escalate.yaml"]


@pytest.mark.parametrize("filename", _intent_files)
def test_intent_golden(jone_router: IntentRouter, filename: str):
    data = _load_golden(filename)
    for case in data["messages"]:
        detected = jone_router.detect(case["user"])
        assert detected == case["expected_intent"], (
            f"[{filename}] '{case['user']}': expected {case['expected_intent']}, got {detected}"
        )


def test_postprocess_golden(jone_postprocessor: Postprocessor):
    data = _load_golden("postprocess.yaml")
    for case in data["samples"]:
        result = jone_postprocessor.process(case["input"])
        assert result == case["expected_clean"], (
            f"Input: '{case['input']}' -> Expected: '{case['expected_clean']}' -> Got: '{result}'"
        )

