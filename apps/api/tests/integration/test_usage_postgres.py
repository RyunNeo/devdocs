from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from test_chat_postgres import postgres_app as postgres_app


def test_postgres_last_quota_slot_and_migration(postgres_app):
    from app.models.usage import DailyUsageCounter, UsageEvent
    from app.models.user import User
    from app.services.usage_service import reserve_operation

    app, migrate = postgres_app
    app.state.settings.daily_chat_limit = 1
    with app.state.session_factory() as db:
        user = User(email="quota-pg@example.com", password_hash="not-a-real-password")
        db.add(user)
        db.commit()
        identifier = user.id
    barrier = Barrier(2)

    def attempt():
        with app.state.session_factory() as db:
            barrier.wait(timeout=10)
            try:
                reserve_operation(db, identifier, "chat", uuid4(), str(uuid4()), app.state.settings)
                db.commit()
                return 200
            except HTTPException as error:
                db.rollback()
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt) for _ in range(2)]
        assert sorted(future.result(timeout=20) for future in futures) == [200, 429]
    with app.state.session_factory() as db:
        assert len(db.scalars(select(UsageEvent)).all()) == 1
        assert db.scalar(select(DailyUsageCounter.used_count)) == 1
    migrate("check")
    migrate("downgrade", "0006_conversations_messages")
    with app.state.session_factory() as db:
        assert db.scalar(select(User.email)) == "quota-pg@example.com"
    migrate("upgrade", "head")
    migrate("check")
