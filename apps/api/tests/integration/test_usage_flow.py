from uuid import uuid4

from sqlalchemy import select
from test_usage_quota import usage_app as usage_app


def test_chat_local_answer_quota_and_resource_deletion(usage_app):
    import time

    from app.models.message import Message
    from app.models.usage import UsageEvent

    app, client = usage_app
    kb = client.post("/knowledge-bases", json={"name": "Usage"}).json()["id"]
    conv = client.post(f"/knowledge-bases/{kb}/conversations", json={}).json()["id"]
    run = str(uuid4())
    started = time.monotonic()
    assert (
        client.post(
            f"/conversations/{conv}/chat/stream", json={"question": "test", "request_id": run}
        ).status_code
        == 200
    )
    assert time.monotonic() - started < 3
    assert (
        client.post(
            f"/conversations/{conv}/chat/stream", json={"question": "test", "request_id": run}
        ).status_code
        == 409
    )
    denied = client.post(
        f"/conversations/{conv}/chat/stream", json={"question": "next", "request_id": str(uuid4())}
    )
    assert denied.status_code == 429
    with app.state.session_factory() as db:
        event = db.scalar(select(UsageEvent))
        assert event.status == "local_completed"
        assert event.attempts == {}
        assert event.durations_ms["total"] >= 0
        assert len(db.scalars(select(Message)).all()) == 2
    assert client.delete(f"/knowledge-bases/{kb}").status_code == 204
    with app.state.session_factory() as db:
        assert db.scalar(select(UsageEvent)).status == "local_completed"


def test_index_reuse_failure_and_quota(usage_app, monkeypatch):
    from app.models.usage import UsageEvent
    from app.rag import embeddings

    class Fake:
        def embed_documents(self, texts):
            return [[1.0] + [0.0] * 1023 for _ in texts]

    app, client = usage_app
    app.state.settings.siliconflow_api_key = None
    monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: Fake())
    kb = client.post("/knowledge-bases", json={"name": "Index"}).json()["id"]
    docs = [
        client.post(
            f"/knowledge-bases/{kb}/documents", files={"file": (f"{i}.txt", str(i).encode())}
        ).json()["id"]
        for i in range(2)
    ]
    assert client.post(f"/documents/{docs[0]}/index").json()["index_status"] == "completed"
    assert client.post(f"/documents/{docs[0]}/index").json()["index_status"] == "completed"
    assert client.post(f"/documents/{docs[1]}/index").status_code == 429
    with app.state.session_factory() as db:
        events = db.scalars(select(UsageEvent)).all()
        assert len(events) == 1 and events[0].status == "completed"


def test_retrieval_miss_after_embedding_is_not_local_only(usage_app, monkeypatch):
    import httpx
    from pydantic import SecretStr

    from app.models.usage import UsageEvent
    from app.rag import chain, embeddings

    app, client = usage_app
    app.state.settings.siliconflow_api_key = SecretStr("fake-only")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [1.0] + [0.0] * 1023}],
                "usage": {"total_tokens": 7},
            },
        )
    )
    monkeypatch.setattr(
        embeddings,
        "make_embeddings",
        lambda settings: embeddings.SiliconFlowEmbeddings(settings, transport),
    )
    monkeypatch.setattr(chain, "query_context", lambda *args: [])
    kb = client.post("/knowledge-bases", json={"name": "Miss"}).json()["id"]
    doc = client.post(
        f"/knowledge-bases/{kb}/documents", files={"file": ("notes.txt", b"text")}
    ).json()["id"]
    assert client.post(f"/documents/{doc}/index").status_code == 200
    conv = client.post(f"/knowledge-bases/{kb}/conversations", json={}).json()["id"]
    assert (
        client.post(
            f"/conversations/{conv}/chat/stream",
            json={"question": "unrelated", "request_id": str(uuid4())},
        ).status_code
        == 200
    )
    with app.state.session_factory() as db:
        event = db.scalar(select(UsageEvent).where(UsageEvent.operation == "chat"))
        assert event.attempts["query_embedding"] == 1
        assert event.status == "completed"


def test_remote_worker_cancellation_keeps_producer_observations(usage_app):
    from uuid import UUID

    from app.core.usage_context import UsageMetrics
    from app.models.usage import UsageEvent
    from app.models.user import User
    from app.services.chat_service import ChatRuntime, cancel_chat_run, claim_chat_run
    from app.services.usage_service import finish_operation, persist_attempt

    app, client = usage_app
    kb = client.post("/knowledge-bases", json={"name": "Remote cancel"}).json()["id"]
    conv = client.post(f"/knowledge-bases/{kb}/conversations", json={}).json()["id"]
    with app.state.session_factory() as db:
        user = db.scalar(select(User)).id
        run = claim_chat_run(db, user, UUID(conv), "question", uuid4(), app.state.settings)
    observed = UsageMetrics(
        attempts={"query_embedding": 1},
        token_usage={"query_embedding": {"known_tokens": 9, "complete": True}},
    )
    assert persist_attempt(app.state.session_factory, run.usage_event_id, observed)
    with app.state.session_factory() as db:
        cancel_chat_run(db, user, UUID(conv), run.run_id, ChatRuntime())
    assert not finish_operation(
        app.state.session_factory, run.usage_event_id, "completed", observed
    )
    with app.state.session_factory() as db:
        event = db.get(UsageEvent, run.usage_event_id)
        assert event.status == "cancelled"
        assert event.token_usage["query_embedding"]["known_tokens"] == 9
