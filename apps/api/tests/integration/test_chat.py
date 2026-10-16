import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.core.config import Settings
    from app.db.base import Base
    from app.main import create_app
    from app.rag import embeddings

    class FakeEmbedding:
        def embed_documents(self, texts):
            return [[1.0] + [0.0] * 1023 for _ in texts]

        async def aembed_query(self, text):
            return [1.0] + [0.0] * 1023

    monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: FakeEmbedding())
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'chat.db'}",
            siliconflow_api_key="fake-key",
            upload_dir=tmp_path / "uploads",
        )
    )
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        client.post(
            "/auth/register", json={"email": "flow@example.com", "password": "Study-safe-2026!"}
        )
        yield client


def setup(client, indexed=True):
    kb = client.post("/knowledge-bases", json={"name": "Flow"}).json()["id"]
    doc = None
    if indexed:
        doc = client.post(
            f"/knowledge-bases/{kb}/documents",
            files={"file": ("react.md", b"# React\n\nComponents use state.\n", "text/plain")},
        ).json()
        assert client.post(f"/documents/{doc['id']}/index").json()["index_status"] == "completed"
    response = client.post(f"/knowledge-bases/{kb}/conversations", json={})
    assert response.status_code == 201
    return kb, response.json()["id"], doc


def frames(response):
    from app.rag.stream_protocol import SSEDecoder

    return [(name, json.loads(data)) for name, data in SSEDecoder().feed(response.content)]


def test_complete_answer_persisted_with_citations(client, monkeypatch):
    from app.rag import chat_model
    from app.rag.chat_model import ProviderEvent

    class FakeChat:
        async def astream(self, messages, deadline):
            yield ProviderEvent("token", {"delta": "组件使用状态 [1]"})
            yield ProviderEvent("finish", {"finish_reason": "stop"})

    monkeypatch.setattr(chat_model, "make_chat_model", lambda settings: FakeChat())
    kb, identifier, doc = setup(client)
    response = client.post(
        f"/conversations/{identifier}/chat/stream",
        json={"question": "组件如何使用状态？", "request_id": str(uuid4())},
    )
    assert response.status_code == 200
    assert [name for name, _ in frames(response) if name != "status"] == [
        "meta",
        "token",
        "citations",
        "done",
    ]
    answer = client.get(f"/conversations/{identifier}").json()["messages"][-1]
    assert answer["status"] == "completed"
    assert answer["citations"][0]["filename"] == "react.md"
    client.delete(f"/documents/{doc['id']}")
    assert (
        client.get(f"/conversations/{identifier}").json()["messages"][-1]["citations"][0][
            "source_status"
        ]
        == "deleted"
    )


def test_empty_library_does_not_call_models(client, monkeypatch):
    from app.rag import chat_model, embeddings

    monkeypatch.setattr(
        chat_model, "make_chat_model", lambda settings: pytest.fail("Model must not be called")
    )
    monkeypatch.setattr(
        embeddings, "make_embeddings", lambda settings: pytest.fail("Embedding must not be called")
    )
    kb, identifier, _ = setup(client, indexed=False)
    response = client.post(
        f"/conversations/{identifier}/chat/stream",
        json={"question": "问题", "request_id": str(uuid4())},
    )
    assert response.status_code == 200
    assert frames(response)[-1][0] == "done"
    assert (
        "未找到足够依据"
        in client.get(f"/conversations/{identifier}").json()["messages"][-1]["content"]
    )


def test_mixed_refusal_replaces_streamed_draft_and_saved_answer(client, monkeypatch):
    from app.rag import chat_model
    from app.rag.chat_model import ProviderEvent
    from app.rag.citations import INSUFFICIENT

    class MixedRefusal:
        async def astream(self, messages, deadline):
            yield ProviderEvent("token", {"delta": "推测的产品定位 [1]。"})
            yield ProviderEvent("token", {"delta": "\n[[INSUFFICIENT_EVIDENCE]]"})
            yield ProviderEvent("finish", {"finish_reason": "stop"})

    monkeypatch.setattr(chat_model, "make_chat_model", lambda settings: MixedRefusal())
    _, identifier, _ = setup(client)
    response = client.post(
        f"/conversations/{identifier}/chat/stream",
        json={"question": "讲解一下产品定位", "request_id": str(uuid4())},
    )
    done = next(data for name, data in frames(response) if name == "done")
    assert done.get("content") == INSUFFICIENT
    saved = client.get(f"/conversations/{identifier}").json()["messages"][-1]
    assert saved["content"] == INSUFFICIENT
    assert saved["citations"] == []


def test_invalid_citation_fails_and_duplicate_is_rejected(client, monkeypatch):
    from app.rag import chat_model
    from app.rag.chat_model import ProviderEvent

    class BadChat:
        async def astream(self, messages, deadline):
            yield ProviderEvent("token", {"delta": "错误来源 [99]"})
            yield ProviderEvent("finish", {"finish_reason": "stop"})

    monkeypatch.setattr(chat_model, "make_chat_model", lambda settings: BadChat())
    _, identifier, _ = setup(client)
    payload = {"question": "问题", "request_id": str(uuid4())}
    response = client.post(f"/conversations/{identifier}/chat/stream", json=payload)
    assert response.status_code == 200
    assert frames(response)[-1][0] == "error"
    assert client.get(f"/conversations/{identifier}").json()["messages"][-1]["status"] == "failed"
    assert client.post(f"/conversations/{identifier}/chat/stream", json=payload).status_code == 409


def test_deleted_source_emits_snapshot_warning_without_refresh(client, monkeypatch):
    import asyncio

    from app.rag import chat_model
    from app.rag.chat_model import ProviderEvent

    _, identifier, document = setup(client)

    class DeleteSource:
        async def astream(self, messages, deadline):
            response = await asyncio.to_thread(client.delete, f"/documents/{document['id']}")
            assert response.status_code == 204
            yield ProviderEvent("token", {"delta": "答案 [1]"})
            yield ProviderEvent("finish", {"finish_reason": "stop"})

    monkeypatch.setattr(chat_model, "make_chat_model", lambda settings: DeleteSource())
    response = client.post(
        f"/conversations/{identifier}/chat/stream",
        json={"question": "问题", "request_id": str(uuid4())},
    )
    citations = next(data for name, data in frames(response) if name == "citations")
    assert citations["items"][0]["source_status"] == "deleted"


def test_large_answer_has_small_done_frame(client, monkeypatch):
    from app.rag import chat_model
    from app.rag.chat_model import ProviderEvent

    class Large:
        async def astream(self, messages, deadline):
            for _ in range(80):
                yield ProviderEvent("token", {"delta": "x" * 1000})
            yield ProviderEvent("token", {"delta": " [1]"})
            yield ProviderEvent("finish", {"finish_reason": "stop"})

    monkeypatch.setattr(chat_model, "make_chat_model", lambda settings: Large())
    _, identifier, _ = setup(client)
    response = client.post(
        f"/conversations/{identifier}/chat/stream",
        json={"question": "问题", "request_id": str(uuid4())},
    )
    done = next(data for name, data in frames(response) if name == "done")
    assert len(json.dumps(done).encode()) < 65536
