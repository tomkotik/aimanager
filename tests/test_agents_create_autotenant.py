from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

import src.api.v1.agents as agents_api
from src.core.schemas import AgentConfig, AgentIdentity, DialoguePolicyConfig, LLMConfig, TenantFullConfig
from src.db import get_db
from src.main import app


@pytest.mark.asyncio
async def test_create_agent_autocreates_tenant_when_missing(monkeypatch: pytest.MonkeyPatch):
    session = AsyncMock()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        # Minimal tenant config for "create from YAML" mode (payload.config is None).
        tenant_cfg = TenantFullConfig(
            agent=AgentConfig(
                id="a1",
                name="Agent",
                identity=AgentIdentity(role="role", persona="persona"),
                llm=LLMConfig(),
            ),
            dialogue_policy=DialoguePolicyConfig(),
            actions=[],
            knowledge={},
        )

        monkeypatch.setattr(agents_api, "load_tenant_config", lambda *_a, **_k: tenant_cfg)
        monkeypatch.setattr(agents_api, "get_tenant_by_slug", AsyncMock(return_value=None))

        tenant_id = uuid4()
        tenant_stub = SimpleNamespace(id=tenant_id, slug="j-one-studio", name="j-one-studio")
        create_tenant_mock = AsyncMock(return_value=tenant_stub)
        monkeypatch.setattr(agents_api, "create_tenant", create_tenant_mock)

        monkeypatch.setattr(agents_api, "get_agent", AsyncMock(return_value=None))

        agent_id = uuid4()
        agent_stub = SimpleNamespace(
            id=agent_id,
            slug="a1",
            name="Agent",
            tenant_id=tenant_id,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        create_agent_mock = AsyncMock(return_value=agent_stub)
        monkeypatch.setattr(agents_api, "create_agent", create_agent_mock)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/agents",
                json={"tenant_slug": "j-one-studio", "agent_slug": "a1"},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["slug"] == "a1"
        assert body["tenant_id"] == str(tenant_id)
        create_tenant_mock.assert_awaited()
    finally:
        app.dependency_overrides.clear()

