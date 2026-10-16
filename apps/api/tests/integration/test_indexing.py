import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from app.core.config import Settings
    from app.db.base import Base
    from app.main import create_app

    app = create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'index.db'}", upload_dir=tmp_path / "uploads")
    )
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        assert (
            client.post(
                "/auth/register",
                json={"email": "index@example.com", "password": "Study-safe-2026!"},
            ).status_code
            == 201
        )
        yield client


def doc(client):
    kb = client.post("/knowledge-bases", json={"name": "向量练习"}).json()["id"]
    response = client.post(
        f"/knowledge-bases/{kb}/documents",
        files={
            "file": ("notes.md", ("# React\n\n" + "组件与状态。" * 800).encode(), "text/plain"),
        },
    )
    assert response.status_code == 201
    return response.json()


def test_missing_key_does_not_claim_success(client):
    document = doc(client)
    response = client.post(f"/documents/{document['id']}/index")
    assert response.status_code == 503
    assert "SILICONFLOW_API_KEY" in response.json()["detail"]
    assert client.get(f"/documents/{document['id']}").json()["index_status"] == "pending"


def test_index_atomic_idempotent_chunks_and_cascade(client, monkeypatch):
    from app.rag import embeddings

    calls = []

    class LocalTestEmbeddings:
        def embed_documents(self, texts):
            calls.append(len(texts))
            return [[1.0] + [0.0] * 1023 for _ in texts]

    monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: LocalTestEmbeddings())
    document = doc(client)
    resource = f"/documents/{document['id']}"
    response = client.post(f"{resource}/index")
    assert response.status_code == 200
    assert response.json()["index_status"] == "completed"
    chunks = client.get(f"{resource}/chunks").json()
    assert chunks["total"] == response.json()["chunk_count"] > 1
    assert chunks["items"][0]["embedding_model"] == "BAAI/bge-m3"
    assert "embedding" not in chunks["items"][0]
    before = list(calls)
    assert client.post(f"{resource}/index").json()["index_status"] == "completed"
    assert calls == before
    assert client.delete(resource).status_code == 204
    assert client.get(f"{resource}/chunks").status_code == 404


def test_embedding_failure_has_no_partial_chunks(client, monkeypatch):
    from app.rag import embeddings

    class Broken:
        def embed_documents(self, texts):
            raise embeddings.EmbeddingError("模型服务请求失败，请稍后重试")

    monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: Broken())
    document = doc(client)
    resource = f"/documents/{document['id']}"
    result = client.post(f"{resource}/index")
    assert result.status_code == 200
    assert result.json()["index_status"] == "failed"
    assert client.get(f"{resource}/chunks").json()["total"] == 0


def test_index_and_chunks_are_owner_scoped(client):
    document = doc(client)
    client.cookies.clear()
    assert (
        client.post(
            "/auth/register",
            json={"email": "other-index@example.com", "password": "Study-safe-2026!"},
        ).status_code
        == 201
    )
    resource = f"/documents/{document['id']}"
    assert client.post(f"{resource}/index").status_code == 404
    assert client.get(f"{resource}/chunks").status_code == 404
    client.cookies.clear()
    assert client.post(f"{resource}/index").status_code == 401


def test_pdf_upload_keeps_pages_and_index_locations(client, text_pdf, monkeypatch):
    from app.rag import embeddings

    class LocalTest:
        def embed_documents(self, texts):
            return [[1.0] + [0.0] * 1023 for _ in texts]

    monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: LocalTest())
    kb = client.post("/knowledge-bases", json={"name": "PDF练习"}).json()["id"]
    result = client.post(
        f"/knowledge-bases/{kb}/documents",
        files={"file": ("notes.pdf", text_pdf, "application/pdf")},
    )
    assert result.status_code == 201 and result.json()["status"] == "parsed"
    resource = f"/documents/{result.json()['id']}"
    assert client.post(f"{resource}/index").json()["index_status"] == "completed"
    assert [
        chunk["metadata"]["page"] for chunk in client.get(f"{resource}/chunks").json()["items"]
    ] == [1, 2]


def test_partial_pdf_has_explicit_warning(client, make_pdf):
    kb = client.post("/knowledge-bases", json={"name": "部分页面"}).json()["id"]
    result = client.post(
        f"/knowledge-bases/{kb}/documents",
        files={"file": ("partial.pdf", make_pdf(["text", ""]), "application/pdf")},
    )
    assert result.json()["status"] == "parsed"
    assert "1 页未提取到文本" in result.json()["parse_warning"]


def test_inflight_index_is_conflict_and_expired_run_can_recover(client, monkeypatch):
    import uuid
    from datetime import datetime, timedelta, timezone

    from app.models.document import Document
    from app.rag import embeddings

    document = doc(client)
    with client.app.state.session_factory() as db:
        stored = db.get(Document, uuid.UUID(document["id"]))
        stored.index_status = "indexing"
        stored.index_run_id = uuid.uuid4()
        stored.index_started_at = datetime.now(timezone.utc)
        db.commit()
    resource = f"/documents/{document['id']}"
    assert client.post(f"{resource}/index").status_code == 409

    class LocalTest:
        def embed_documents(self, texts):
            return [[1.0] + [0.0] * 1023 for _ in texts]

    monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: LocalTest())
    with client.app.state.session_factory() as db:
        stored = db.get(Document, uuid.UUID(document["id"]))
        stored.index_started_at = datetime.now(timezone.utc) - timedelta(seconds=301)
        db.commit()
    assert client.post(f"{resource}/index").json()["index_status"] == "completed"


def test_delete_during_embedding_cannot_resurrect_document(client, monkeypatch):
    from app.rag import embeddings

    document = doc(client)
    resource = f"/documents/{document['id']}"

    class DeleteDuringCall:
        def embed_documents(self, texts):
            assert client.delete(resource).status_code == 204
            return [[1.0] + [0.0] * 1023 for _ in texts]

    monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: DeleteDuringCall())
    assert client.post(f"{resource}/index").status_code == 404
    assert client.get(resource).status_code == 404


def test_superseded_run_cannot_publish_old_vectors(client, monkeypatch):
    import uuid

    from app.models.document import Document
    from app.rag import embeddings

    document = doc(client)
    replacement = uuid.uuid4()

    class SupersedeDuringCall:
        def embed_documents(self, texts):
            with client.app.state.session_factory() as db:
                stored = db.get(Document, uuid.UUID(document["id"]))
                stored.index_run_id = replacement
                db.commit()
            return [[1.0] + [0.0] * 1023 for _ in texts]

    monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: SupersedeDuringCall())
    resource = f"/documents/{document['id']}"
    assert client.post(f"{resource}/index").status_code == 409
    assert client.get(f"{resource}/chunks").json()["total"] == 0
    with client.app.state.session_factory() as db:
        assert db.get(Document, uuid.UUID(document["id"])).index_run_id == replacement


def test_publish_failure_preserves_previous_chunks_atomically(client, monkeypatch):
    import uuid

    from sqlalchemy import event

    from app.models.chunk import DocumentChunk
    from app.models.document import Document
    from app.rag import embeddings

    class LocalTest:
        def embed_documents(self, texts):
            return [[1.0] + [0.0] * 1023 for _ in texts]

    monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: LocalTest())
    document = doc(client)
    resource = f"/documents/{document['id']}"
    assert client.post(f"{resource}/index").json()["index_status"] == "completed"
    before = client.get(f"{resource}/chunks").json()["items"]
    with client.app.state.session_factory() as db:
        stored = db.get(Document, uuid.UUID(document["id"]))
        stored.index_fingerprint = "old-version"
        db.commit()
    fired = False

    def fail_new_chunks(session, context, instances):
        nonlocal fired
        if not fired and any(isinstance(item, DocumentChunk) for item in session.new):
            fired = True
            raise RuntimeError("forced publish failure")

    event.listen(client.app.state.session_factory, "before_flush", fail_new_chunks)
    try:
        result = client.post(f"{resource}/index").json()
    finally:
        event.remove(client.app.state.session_factory, "before_flush", fail_new_chunks)
    assert result["index_status"] == "failed"
    after = client.get(f"{resource}/chunks").json()["items"]
    assert [item["id"] for item in after] == [item["id"] for item in before]
