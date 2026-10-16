from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from test_conversations import client as base_client


@pytest.fixture
def client(tmp_path):
    yield from base_client.__wrapped__(tmp_path)


def make_history(client, count=1, messages=1):
    from app.models.conversation import Conversation
    from app.models.message import Message

    kb = client.post("/knowledge-bases", json={"name": "History"}).json()["id"]
    identifiers = []
    for index in range(count):
        identifier = client.post(f"/knowledge-bases/{kb}/conversations", json={}).json()["id"]
        identifiers.append(identifier)
        with client.app.state.session_factory() as db:
            db.get(Conversation, UUID(identifier)).updated_at = datetime.now(
                timezone.utc
            ) + timedelta(seconds=index)
            db.add_all(
                Message(
                    conversation_id=UUID(identifier),
                    sequence=i,
                    role="user",
                    status="completed",
                    content=f"{index}-{i}-" + "长" * 100,
                )
                for i in range(1, messages + 1)
            )
            db.commit()
    return kb, identifiers


def test_owned_nonempty_history_is_sorted_and_bounded(client):
    kb, ids = make_history(client, count=3)
    client.post(f"/knowledge-bases/{kb}/conversations", json={})
    response = client.get(f"/knowledge-bases/{kb}/conversations?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert [c["id"] for c in data["items"]] == list(reversed(ids))[:2]
    assert all(len(c["title"]) <= 40 and len(c["last_question"]) <= 80 for c in data["items"])
    assert all("messages" not in c and "citations" not in c for c in data["items"])
    assert (
        client.get(f"/knowledge-bases/{kb}/conversations?offset=2").json()["items"][0]["id"]
        == ids[0]
    )


def test_message_cursor_has_no_gaps_or_duplicates(client):
    _, ids = make_history(client, messages=86)
    url = f"/conversations/{ids[0]}"
    latest = client.get(url).json()
    previous = client.get(url + "?before_sequence=47").json()
    first = client.get(url + "?before_sequence=7").json()
    assert latest["has_older"] and previous["has_older"]
    assert first["has_older"] is False
    sequence = [m["sequence"] for p in [first, previous, latest] for m in p["messages"]]
    assert sequence == list(range(1, 87))
    assert client.get(url + "?limit=0").status_code == 422
    assert client.get(url + "?before_sequence=0").status_code == 422


def test_legacy_failed_drafts_are_not_returned(client):
    from app.models.message import Message

    _, ids = make_history(client)
    with client.app.state.session_factory() as db:
        for index, status in enumerate(["failed", "cancelled", "streaming"], 2):
            db.add(
                Message(
                    conversation_id=UUID(ids[0]),
                    sequence=index,
                    role="assistant",
                    status=status,
                    content="private-draft",
                    citations=[{"invalid": "legacy private reference"}],
                )
            )
        db.commit()
    result = client.get(f"/conversations/{ids[0]}")
    assert result.status_code == 200
    assert result.json()["messages"][0]["content"]
    assert all(m["content"] == "" and m["citations"] == [] for m in result.json()["messages"][1:])
    with client.app.state.session_factory() as db:
        from sqlalchemy import select

        assert (
            db.scalar(select(Message.content).where(Message.role == "assistant")) == "private-draft"
        )


def test_history_is_owner_scoped(client):
    kb, ids = make_history(client)
    assert client.get(f"/knowledge-bases/{kb}/conversations?limit=0").status_code == 422
    assert client.get(f"/knowledge-bases/{kb}/conversations?offset=-1").status_code == 422
    client.cookies.clear()
    assert client.get(f"/knowledge-bases/{kb}/conversations").status_code == 401
    client.post(
        "/auth/register", json={"email": "foreign@example.com", "password": "Study-safe-2026!"}
    )
    assert client.get(f"/knowledge-bases/{kb}/conversations").status_code == 404
    assert client.get(f"/conversations/{ids[0]}?before_sequence=10").status_code == 404
