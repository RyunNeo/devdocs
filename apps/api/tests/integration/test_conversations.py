import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from app.core.config import Settings
    from app.db.base import Base
    from app.main import create_app

    application = create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'chat.db'}", siliconflow_api_key=None)
    )
    Base.metadata.create_all(application.state.engine)
    with TestClient(application) as client:
        client.post(
            "/auth/register", json={"email": "chat@example.com", "password": "Study-safe-2026!"}
        )
        yield client


def test_create_read_owned_conversation(client):
    kb = client.post("/knowledge-bases", json={"name": "Chat"}).json()["id"]
    response = client.post(f"/knowledge-bases/{kb}/conversations", json={})
    assert response.status_code == 201
    identifier = response.json()["id"]
    detail = client.get(f"/conversations/{identifier}")
    assert detail.status_code == 200
    assert detail.json()["messages"] == []
    client.cookies.clear()
    assert client.get(f"/conversations/{identifier}").status_code == 401
    client.post(
        "/auth/register", json={"email": "other-chat@example.com", "password": "Study-safe-2026!"}
    )
    assert client.get(f"/conversations/{identifier}").status_code == 404


def test_read_latest_40_messages(client):
    from uuid import UUID

    from app.models.message import Message

    kb = client.post("/knowledge-bases", json={"name": "History"}).json()["id"]
    response = client.post(f"/knowledge-bases/{kb}/conversations", json={})
    assert response.status_code == 201
    identifier = response.json()["id"]
    with client.app.state.session_factory() as db:
        db.add_all(
            Message(
                conversation_id=UUID(identifier),
                sequence=i,
                role="user",
                content=str(i),
                status="completed",
            )
            for i in range(1, 43)
        )
        db.commit()
    detail = client.get(f"/conversations/{identifier}").json()
    assert [m["sequence"] for m in detail["messages"]] == list(range(3, 43))
    assert detail["has_older"] is True
