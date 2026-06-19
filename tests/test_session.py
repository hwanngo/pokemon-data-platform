"""The session_scope() context manager must always close its session (so callers
stop leaking connections via the discarded `next(get_db())` generator)."""

import pytest

from src.models import base


def test_session_scope_closes_on_normal_exit(monkeypatch):
    closed = []

    class FakeSession:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(base, "SessionLocal", lambda: FakeSession())

    with base.session_scope() as db:
        assert isinstance(db, FakeSession)

    assert closed == [True]


def test_session_scope_closes_on_exception(monkeypatch):
    closed = []

    class FakeSession:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(base, "SessionLocal", lambda: FakeSession())

    with pytest.raises(ValueError), base.session_scope():
        raise ValueError("boom")

    assert closed == [True]
