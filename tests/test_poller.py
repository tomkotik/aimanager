from __future__ import annotations

from unittest.mock import patch

from src.workers.poller import poll_channels_task


class _FakeResult:
    def all(self):
        return []


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, *_args, **_kwargs):
        return _FakeResult()

    async def commit(self):
        return None


def test_poll_channels_task_runs_without_errors_with_empty_db():
    def _fake_async_session():
        return _FakeSession()

    with patch("src.db.async_session", new=_fake_async_session):
        poll_channels_task()

