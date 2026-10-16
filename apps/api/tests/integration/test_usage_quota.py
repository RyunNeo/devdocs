from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture
def usage_app(tmp_path):
    from app.core.config import Settings
    from app.db.base import Base
    from app.main import create_app

    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'usage.db'}",
            upload_dir=tmp_path / "uploads",
            daily_chat_limit=1,
            daily_index_limit=1,
            siliconflow_api_key=None,
        )
    )
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        client.post(
            "/auth/register", json={"email": "usage@example.com", "password": "Study-safe-2026!"}
        )
        yield app, client
    app.state.engine.dispose()


def test_day_defaults_and_validation():
    from app.core.config import Settings
    from app.services.usage_service import quota_reset_at, usage_day

    assert Settings().daily_chat_limit == 50
    assert Settings().daily_index_limit == 20
    with pytest.raises(ValueError):
        Settings(daily_chat_limit=0)
    before = datetime(2026, 10, 15, 15, 59, tzinfo=timezone.utc)
    assert usage_day(before).isoformat() == "2026-10-15"
    assert usage_day(before.replace(hour=16)).isoformat() == "2026-10-16"
    assert quota_reset_at(before).isoformat() == "2026-10-15T16:00:00+00:00"


def test_atomic_reservation_and_rollback(usage_app):
    from app.models.usage import DailyUsageCounter, UsageEvent
    from app.models.user import User
    from app.services.usage_service import reserve_operation

    app, _ = usage_app
    with app.state.session_factory() as db:
        user = db.scalar(select(User)).id
        reserve_operation(db, user, "chat", uuid4(), str(uuid4()), app.state.settings)
        db.rollback()
        assert db.scalar(select(UsageEvent)) is None
        reserve_operation(db, user, "chat", uuid4(), str(uuid4()), app.state.settings)
        db.commit()
        with pytest.raises(HTTPException) as error:
            reserve_operation(db, user, "chat", uuid4(), str(uuid4()), app.state.settings)
        assert error.value.status_code == 429
        assert error.value.headers["X-Error-Code"] == "daily_quota_exceeded"
        db.rollback()
        assert db.scalar(select(DailyUsageCounter.used_count)) == 1


def test_finish_is_idempotent_and_usage_unknown(usage_app):
    from app.core.usage_context import UsageMetrics
    from app.models.user import User
    from app.services.usage_service import (
        finish_operation,
        normalize_token_usage,
        reserve_operation,
    )

    assert (
        normalize_token_usage({"prompt_tokens": True, "completion_tokens": -1})["complete"] is False
    )
    assert (
        normalize_token_usage({"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8})[
            "known_tokens"
        ]
        == 8
    )
    app, _ = usage_app
    with app.state.session_factory() as db:
        user = db.scalar(select(User)).id
        event = reserve_operation(db, user, "chat", uuid4(), str(uuid4()), app.state.settings)
        identifier = event.id
        db.commit()
    assert finish_operation(
        app.state.session_factory, identifier, "failed", UsageMetrics(), "timeout"
    )
    assert not finish_operation(app.state.session_factory, identifier, "completed", UsageMetrics())


def test_midnight_and_expired_record_cannot_be_resurrected(usage_app):
    from datetime import timedelta

    from app.core.usage_context import UsageMetrics
    from app.models.usage import DailyUsageCounter, UsageEvent
    from app.models.user import User
    from app.services.usage_service import expire_usage_events, finish_operation, reserve_operation

    app, _ = usage_app
    before = datetime(2026, 10, 15, 15, 59, tzinfo=timezone.utc)
    with app.state.session_factory() as db:
        user = db.scalar(select(User)).id
        first = reserve_operation(
            db, user, "chat", uuid4(), str(uuid4()), app.state.settings, now=before
        )
        first_id = first.id
        db.commit()
        reserve_operation(
            db,
            user,
            "chat",
            uuid4(),
            str(uuid4()),
            app.state.settings,
            now=before + timedelta(minutes=2),
        )
        db.commit()
        assert len(db.scalars(select(DailyUsageCounter)).all()) == 2
        assert (
            expire_usage_events(db, user, before + timedelta(seconds=300), app.state.settings) == 1
        )
        db.commit()
    assert not finish_operation(app.state.session_factory, first_id, "completed", UsageMetrics())
    with app.state.session_factory() as db:
        assert db.get(UsageEvent, first_id).status == "interrupted"
        assert db.get(UsageEvent, first_id).quota_day.isoformat() == "2026-10-15"


def test_cancelled_event_accepts_known_metrics_without_changing_terminal_state(usage_app):
    from app.core.usage_context import UsageMetrics
    from app.models.usage import UsageEvent
    from app.models.user import User
    from app.services.usage_service import finish_operation, reserve_operation

    app, _ = usage_app
    with app.state.session_factory() as db:
        user = db.scalar(select(User)).id
        event = reserve_operation(db, user, "chat", uuid4(), str(uuid4()), app.state.settings)
        identifier = event.id
        db.commit()
    assert finish_operation(
        app.state.session_factory, identifier, "cancelled", UsageMetrics(), "cancelled"
    )
    metrics = UsageMetrics(
        attempts={"query_embedding": 1},
        token_usage={"query_embedding": {"known_tokens": 9, "complete": True}},
    )
    assert not finish_operation(app.state.session_factory, identifier, "completed", metrics)
    assert not finish_operation(app.state.session_factory, identifier, "failed", UsageMetrics())
    with app.state.session_factory() as db:
        event = db.get(UsageEvent, identifier)
        assert event.status == "cancelled" and event.error_code == "cancelled"
        assert event.token_usage["query_embedding"]["known_tokens"] == 9
