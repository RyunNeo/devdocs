import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from app.core.config import Settings
    from app.db.base import Base
    from app.main import create_app

    # Tests never write into the user's upload directory.
    app = create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'docs.db'}", upload_dir=tmp_path / "uploads")
    )
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        assert (
            client.post(
                "/auth/register",
                json={
                    "email": "docs@example.com",
                    "password": "Study-safe-2026!",
                },
            ).status_code
            == 201
        )
        yield client


def knowledge(client, name="文档练习"):
    return client.post("/knowledge-bases", json={"name": name}).json()["id"]


def upload(client, kb, name="notes.md", content=None):
    content = "# React\r\n组件学习\r\n".encode() if content is None else content
    return client.post(
        f"/knowledge-bases/{kb}/documents",
        files={
            "file": (name, content, "application/octet-stream"),
        },
    )


def test_upload_list_preview_duplicate_and_delete(client):
    kb = knowledge(client)
    response = upload(client, kb, "../../notes.MD")
    assert response.status_code == 201
    doc = response.json()
    assert doc["filename"] == "notes.MD"
    assert doc["status"] == "parsed" and doc["character_count"] > 0
    assert "storage_key" not in doc and "extracted_text" not in doc
    detail = client.get(f"/documents/{doc['id']}").json()
    assert detail["text_preview"] == "# React\n组件学习\n"
    assert detail["preview_truncated"] is False
    listed = client.get(f"/knowledge-bases/{kb}/documents").json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == doc["id"]
    assert upload(client, kb, "renamed.txt").status_code == 409
    assert upload(client, knowledge(client, "另一知识库")).status_code == 201
    assert client.get("/documents/summary").json()["total"] == 2
    assert client.delete(f"/documents/{doc['id']}").status_code == 204
    assert client.get(f"/documents/{doc['id']}").status_code == 404
    assert client.get(f"/knowledge-bases/{kb}/documents").json()["total"] == 0


@pytest.mark.parametrize(
    "name,data,status",
    [
        ("a.json", b"plain text", 400),
        ("a.txt", b"", 400),
        ("a.txt", b"x" * (10 * 1024 * 1024 + 1), 413),
    ],
    ids=["unsupported", "empty", "too-large"],
)
def test_invalid_upload_does_not_persist_record(client, name, data, status):
    kb = knowledge(client)
    assert upload(client, kb, name, data).status_code == status
    assert client.get(f"/knowledge-bases/{kb}/documents").json()["total"] == 0
    assert not list(client.app.state.settings.upload_dir.glob("**/*.bin"))


@pytest.mark.parametrize(
    "content,reason",
    [
        (b"\xff\xfe\x00", "UTF-8"),
        (b"binary\x00data", "二进制"),
        (b" \r\n\t", "有效文本"),
    ],
)
def test_parse_failure_is_visible_and_retry_preserves_record(client, content, reason):
    kb = knowledge(client)
    response = upload(client, kb, "bad.txt", content)
    assert response.status_code == 201
    doc = response.json()
    assert doc["status"] == "failed" and reason in doc["error_message"]
    retried = client.post(f"/documents/{doc['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["id"] == doc["id"] and retried.json()["status"] == "failed"
    assert client.get(f"/documents/{doc['id']}").json()["text_preview"] is None


def test_bom_preview_limit_and_parsed_retry(client):
    kb = knowledge(client)
    doc = upload(client, kb, "bom.txt", b"\xef\xbb\xbf" + b"a" * 21000).json()
    assert doc["status"] == "parsed" and doc["character_count"] == 21000
    detail = client.get(f"/documents/{doc['id']}").json()
    assert len(detail["text_preview"]) == 20000 and detail["preview_truncated"]
    assert client.post(f"/documents/{doc['id']}/retry").json()["status"] == "parsed"


def test_every_document_route_is_owner_scoped(client):
    kb = knowledge(client)
    doc = upload(client, kb).json()
    client.cookies.clear()
    assert (
        client.post(
            "/auth/register",
            json={
                "email": "other@example.com",
                "password": "Study-safe-2026!",
            },
        ).status_code
        == 201
    )
    assert upload(client, kb).status_code == 404
    assert client.get(f"/knowledge-bases/{kb}/documents").status_code == 404
    assert client.get(f"/documents/{doc['id']}").status_code == 404
    assert client.post(f"/documents/{doc['id']}/retry").status_code == 404
    assert client.delete(f"/documents/{doc['id']}").status_code == 404
    assert client.get("/documents/summary").json()["total"] == 0
    client.cookies.clear()
    assert upload(client, kb).status_code == 401
    assert client.get("/documents/summary").status_code == 401


def test_private_files_and_knowledge_base_cascade(client):
    kb = knowledge(client)
    doc = upload(client, kb).json()
    root = client.app.state.settings.upload_dir
    files = list(root.glob("**/*.bin"))
    assert len(files) == 1 and "notes" not in files[0].name
    assert client.get(f"/storage/uploads/{files[0].name}").status_code == 404
    assert client.delete(f"/knowledge-bases/{kb}").status_code == 204
    assert client.get(f"/documents/{doc['id']}").status_code == 404
    assert not list(root.glob("**/*.bin"))


def test_failed_storage_cleanup_is_durable_and_retryable(client, monkeypatch):
    from sqlalchemy import select

    from app.models.document import StorageCleanupTask
    from app.services import document_storage

    kb = knowledge(client)
    doc = upload(client, kb).json()
    original = document_storage.remove_file
    monkeypatch.setattr(
        document_storage,
        "remove_file",
        lambda *args: (_ for _ in ()).throw(PermissionError("private path must not be echoed")),
    )
    assert client.delete(f"/documents/{doc['id']}").status_code == 204
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(StorageCleanupTask)).all()) == 1
        monkeypatch.setattr(document_storage, "remove_file", original)
        document_storage.drain_cleanup(db, client.app.state.settings)
        assert not db.scalars(select(StorageCleanupTask)).all()
    assert not list(client.app.state.settings.upload_dir.glob("**/*.bin"))


def test_pending_record_recovers_and_pagination_is_bounded(client):
    from uuid import UUID

    from sqlalchemy import select

    from app.models.document import Document

    kb = knowledge(client)
    doc = upload(client, kb).json()
    with client.app.state.session_factory() as db:
        stored = db.scalar(select(Document).where(Document.id == UUID(doc["id"])))
        stored.status = "pending"
        stored.extracted_text = None
        stored.character_count = 0
        db.commit()
    assert client.post(f"/documents/{doc['id']}/retry").json()["status"] == "parsed"
    assert upload(client, kb, "two.txt", b"second").status_code == 201
    first = client.get(f"/knowledge-bases/{kb}/documents?limit=1&offset=0").json()
    second = client.get(f"/knowledge-bases/{kb}/documents?limit=1&offset=1").json()
    assert first["total"] == 2 and first["items"][0]["id"] != second["items"][0]["id"]
    assert client.get(f"/knowledge-bases/{kb}/documents?limit=101").status_code == 422


def test_request_body_limit_without_content_length(client):
    kb = knowledge(client)
    boundary = "test-boundary"

    def body():
        yield (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            'filename="large.txt"\r\n\r\n'
        ).encode()
        for _ in range(170):
            yield b"a" * (64 * 1024)
        yield f"\r\n--{boundary}--\r\n".encode()

    response = client.post(
        f"/knowledge-bases/{kb}/documents",
        content=body(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 413
    assert client.get(f"/knowledge-bases/{kb}/documents").json()["total"] == 0


def test_storage_path_rejects_traversal_and_symlink(client, tmp_path):
    from app.services.document_storage import file_path

    with pytest.raises(ValueError):
        file_path(client.app.state.settings, "../../private")
    root = client.app.state.settings.upload_dir
    root.mkdir(exist_ok=True)
    key = "a" * 32 + ".bin"
    try:
        (root / key).symlink_to(tmp_path / "outside.txt")
    except OSError:
        pytest.skip("Symlink permission unavailable on Windows")
    with pytest.raises(ValueError):
        file_path(client.app.state.settings, key)


def test_metadata_list_does_not_select_document_body(client):
    from sqlalchemy import event

    kb = knowledge(client)
    assert upload(client, kb).status_code == 201
    queries = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(client.app.state.engine, "before_cursor_execute", capture)
    try:
        assert client.get(f"/knowledge-bases/{kb}/documents").status_code == 200
    finally:
        event.remove(client.app.state.engine, "before_cursor_execute", capture)
    row_queries = [
        query for query in queries if "FROM documents" in query and "count(" not in query
    ]
    assert row_queries and all("documents.extracted_text" not in query for query in row_queries)


def test_duplicate_rollback_leaves_retryable_cleanup_on_unlink_failure(client, monkeypatch):
    from sqlalchemy import select

    from app.models.document import StorageCleanupTask
    from app.services import document_storage

    kb = knowledge(client)
    assert upload(client, kb).status_code == 201
    original = document_storage.remove_file

    def fail(*args):
        raise PermissionError("forced cleanup failure")

    monkeypatch.setattr(document_storage, "remove_file", fail)
    assert upload(client, kb, "same.txt").status_code == 409
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(StorageCleanupTask)).all()) == 1
        monkeypatch.setattr(document_storage, "remove_file", original)
        document_storage.drain_cleanup(db, client.app.state.settings)
    assert len(list(client.app.state.settings.upload_dir.glob("*.bin"))) == 1
