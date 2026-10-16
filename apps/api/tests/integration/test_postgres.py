import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Local PostgreSQL URL not set")
def test_expired_session_is_rejected_in_non_utc_database_timezone():
    from app.core.config import Settings
    from app.main import create_app
    from app.models.session import AuthSession
    from app.models.user import User

    application = create_app(Settings(database_url=os.environ["TEST_DATABASE_URL"]))

    @event.listens_for(application.state.engine, "connect")
    def set_timezone(connection, record):
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'Asia/Shanghai'")
        connection.commit()

    email = f"timezone-{uuid.uuid4().hex}@example.com"
    try:
        with TestClient(application) as client:
            assert (
                client.post(
                    "/auth/register",
                    json={
                        "email": email,
                        "password": "Study-safe-2026!",
                    },
                ).status_code
                == 201
            )
            with application.state.session_factory() as db:
                user = db.scalar(select(User).where(User.email == email))
                session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
                session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
                db.commit()
            assert client.get("/auth/me").status_code == 401
    finally:
        with application.state.session_factory() as db:
            db.execute(delete(User).where(User.email == email))
            db.commit()
        application.state.engine.dispose()
