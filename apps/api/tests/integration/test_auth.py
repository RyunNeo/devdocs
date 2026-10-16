from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture
def client(tmp_path):
    from app import main

    assert hasattr(main, "create_app"), "Stage 1 application factory is not implemented"
    from app.core.config import Settings
    from app.db.base import Base

    application = main.create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'auth.db'}",
            allowed_origins=["http://localhost:3000"],
            cookie_secure=False,
        )
    )
    Base.metadata.create_all(application.state.engine)
    with TestClient(application, base_url="http://localhost:8000") as test_client:
        yield test_client


def register(client, email="learner@example.com"):
    return client.post("/auth/register", json={"email": email, "password": "Study-safe-2026!"})


def test_health_does_not_require_login(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_registration_sets_private_cookie_and_hides_password(client):
    result = register(client)
    assert result.status_code == 201
    assert result.json()["user"]["email"] == "learner@example.com"
    assert "password" not in result.text
    cookie = result.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/auth/me").status_code == 200


def test_password_and_session_are_not_stored_in_plaintext(client):
    register(client)
    from app.models.session import AuthSession
    from app.models.user import User

    with client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        session = db.scalar(select(AuthSession))
        assert user.password_hash.startswith("$argon2")
        assert user.password_hash != "Study-safe-2026!"
        assert session.token_hash != client.cookies.get("devdocs_session")


def test_duplicate_normalized_email_is_rejected(client):
    assert register(client, "LEARNER@example.com").status_code == 201
    assert register(client).status_code == 409


def test_bad_login_does_not_reveal_account_existence(client):
    register(client)
    known = client.post("/auth/login", json={"email": "learner@example.com", "password": "wrong"})
    unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


def test_logout_revokes_copied_cookie(client):
    register(client)
    token = client.cookies.get("devdocs_session")
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Cookie": f"devdocs_session={token}"}).status_code == 401


def test_login_works_after_logout(client):
    register(client)
    client.post("/auth/logout")
    response = client.post(
        "/auth/login",
        json={
            "email": "LEARNER@example.com",
            "password": "Study-safe-2026!",
        },
    )
    assert response.status_code == 200
    assert client.get("/auth/me").json()["email"] == "learner@example.com"


def test_tampered_and_missing_cookies_cannot_read_current_user(client):
    assert client.get("/auth/me").status_code == 401
    client.cookies.set("devdocs_session", "forged")
    assert client.get("/auth/me").status_code == 401


def test_expired_cookie_is_rejected(client):
    register(client)
    from app.models.session import AuthSession

    with client.app.state.session_factory() as db:
        session = db.scalar(select(AuthSession))
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.get("/auth/me").status_code == 401


def test_users_read_only_their_own_identity(client):
    first_id = register(client).json()["user"]["id"]
    client.post("/auth/logout")
    second_id = register(client, "second@example.com").json()["user"]["id"]
    assert first_id != second_id
    assert client.get("/auth/me").json()["id"] == second_id


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "Study-safe-2026!"},
        {"email": "learner@example.com", "password": "short"},
        {"email": "learner@example.com", "password": "x" * 129},
    ],
)
def test_invalid_registration_is_rejected_without_echoing_password(client, payload):
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 422
    assert f'"{payload["password"]}"' not in response.text


def test_cross_origin_mutation_is_rejected(client):
    response = client.post(
        "/auth/register",
        headers={"Origin": "https://evil.example"},
        json={
            "email": "learner@example.com",
            "password": "Study-safe-2026!",
        },
    )
    assert response.status_code == 403
    assert register(client).status_code == 201


def test_allowed_origin_can_register(client):
    response = client.post(
        "/auth/register",
        headers={"Origin": "http://localhost:3000"},
        json={
            "email": "learner@example.com",
            "password": "Study-safe-2026!",
        },
    )
    assert response.status_code == 201
