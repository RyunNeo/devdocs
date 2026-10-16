import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Local PostgreSQL URL not set")
def test_migration_and_name_constraint_on_isolated_postgres_database(
    tmp_path, monkeypatch, make_pdf
):
    from app.core.config import Settings
    from app.main import create_app
    from app.models.knowledge_base import KnowledgeBase
    from app.models.user import User

    base_url = make_url(os.environ["TEST_DATABASE_URL"])
    admin_url = base_url.set(drivername="postgresql", database="postgres")
    database_name = f"devdocs_kb_test_{uuid.uuid4().hex[:12]}"
    isolated_url = base_url.set(database=database_name).render_as_string(hide_password=False)
    api_root = Path(__file__).resolve().parents[2]
    admin = psycopg.connect(admin_url.render_as_string(hide_password=False), autocommit=True)
    application = None
    created = False
    try:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
        created = True
        environment = {**os.environ, "DATABASE_URL": isolated_url}
        for arguments in [["upgrade", "0002_knowledge_bases"]]:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", *arguments],
                cwd=api_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
        application = create_app(
            Settings(database_url=isolated_url, upload_dir=tmp_path / "uploads")
        )
        with TestClient(application) as client:
            assert (
                client.post(
                    "/auth/register",
                    json={
                        "email": "migration@example.com",
                        "password": "Study-safe-2026!",
                    },
                ).status_code
                == 201
            )
            response = client.post("/knowledge-bases", json={"name": " React 学习 "})
            assert response.status_code == 201
            resource = f"/knowledge-bases/{response.json()['id']}"
            with application.state.session_factory() as db:
                knowledge = db.scalar(select(KnowledgeBase))
                knowledge.name_key = "react 学习"
                db.commit()
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "0004_documents"],
                cwd=api_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            from sqlalchemy import text

            legacy_id = uuid.uuid4()
            with application.state.engine.begin() as connection:
                connection.execute(
                    text("""INSERT INTO documents
                    (id, knowledge_base_id, user_id, filename, file_type, size_bytes, content_hash,
                     storage_key, status, error_message, extracted_text, character_count,
                     created_at, updated_at)
                    VALUES (:id, :kb, :user, 'legacy.txt', 'txt', 12, :hash, :key, 'parsed', NULL,
                            'legacy notes', 12, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""),
                    {
                        "id": legacy_id,
                        "kb": knowledge.id,
                        "user": knowledge.user_id,
                        "hash": "a" * 64,
                        "key": uuid.uuid4().hex + ".bin",
                    },
                )
            for arguments in [["upgrade", "head"], ["check"]]:
                result = subprocess.run(
                    [sys.executable, "-m", "alembic", *arguments],
                    cwd=api_root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert result.returncode == 0, result.stderr
            assert client.get(f"/documents/{legacy_id}").json()["index_status"] == "pending"
            nul = client.post(
                f"{resource}/documents",
                files={"file": ("nul.pdf", make_pdf(["hello\\000world"]), "application/pdf")},
            )
            assert nul.status_code == 201 and nul.json()["status"] == "failed"
            assert client.post("/knowledge-bases", json={"name": "REACT学习"}).status_code == 409
            # Bypass API checks to prove the database itself enforces uniqueness.
            with application.state.session_factory() as db:
                user = db.scalar(select(User))
                knowledge = db.scalar(select(KnowledgeBase))
                assert knowledge.name == "React 学习"
                assert knowledge.name_key == "react学习"
                db.add(KnowledgeBase(user_id=user.id, name="react学习", name_key="react学习"))
                with pytest.raises(IntegrityError):
                    db.commit()
                db.rollback()
            assert client.patch(resource, json={"description": "API 已验证"}).status_code == 200
            assert client.get("/knowledge-bases").json()["total"] == 1
            from concurrent.futures import ThreadPoolExecutor

            def upload_document():
                return client.post(
                    f"{resource}/documents",
                    files={
                        "file": ("postgres.md", "# PostgreSQL\n迁移与并发".encode(), "text/plain"),
                    },
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: upload_document(), range(2)))
            assert sorted(response.status_code for response in responses) == [201, 409]
            document = next(
                response.json() for response in responses if response.status_code == 201
            )
            assert document["status"] == "parsed"
            from app.models.chunk import DocumentChunk
            from app.rag import embeddings

            class LocalVectorTest:
                def embed_documents(self, texts):
                    return [[1.0] + [0.0] * 1023 for _ in texts]

            monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: LocalVectorTest())
            indexed = client.post(f"/documents/{document['id']}/index")
            assert indexed.status_code == 200 and indexed.json()["index_status"] == "completed"
            with application.state.session_factory() as db:
                distance = db.scalar(
                    select(DocumentChunk.embedding.cosine_distance([1.0] + [0.0] * 1023))
                )
                assert distance == 0.0
            from sqlalchemy.exc import DBAPIError

            with application.state.engine.connect() as connection:
                with pytest.raises(DBAPIError):
                    connection.execute(text("SELECT '[1,2,3]'::vector(1024)"))
            from threading import Event

            started, release = Event(), Event()
            concurrent = client.post(
                f"{resource}/documents",
                files={"file": ("concurrent.txt", b"concurrent sample", "text/plain")},
            ).json()

            class BlockingProvider:
                def embed_documents(self, texts):
                    started.set()
                    assert release.wait(10)
                    return [[1.0] + [0.0] * 1023 for _ in texts]

            monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: BlockingProvider())
            index_url = f"/documents/{concurrent['id']}/index"
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(client.post, index_url)
                try:
                    assert started.wait(5)
                    assert client.post(index_url).status_code == 409
                    assert client.delete(f"/documents/{concurrent['id']}").status_code == 204
                finally:
                    release.set()
                assert future.result(timeout=10).status_code == 404
            from app.models.document import Document

            replacement = uuid.uuid4()

            class SupersededFailure:
                def embed_documents(self, texts):
                    with application.state.session_factory() as db:
                        stored = db.get(Document, legacy_id)
                        stored.index_run_id = replacement
                        db.commit()
                    raise embeddings.EmbeddingError("forced old worker failure")

            monkeypatch.setattr(embeddings, "make_embeddings", lambda settings: SupersededFailure())
            assert client.post(f"/documents/{legacy_id}/index").status_code == 409
            with application.state.session_factory() as db:
                assert db.get(Document, legacy_id).index_run_id == replacement
                assert db.get(Document, legacy_id).index_status == "indexing"
            assert (
                client.get(f"/documents/{document['id']}")
                .json()["text_preview"]
                .startswith("# PostgreSQL")
            )
            assert client.delete(resource).status_code == 204
            assert client.get(f"/documents/{document['id']}").status_code == 404
            with application.state.session_factory() as db:
                assert not db.scalars(select(DocumentChunk)).all()
            assert not list((tmp_path / "uploads").glob("*.bin"))
            assert client.get(resource).status_code == 404
        application.state.engine.dispose()
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0001_auth"],
            cwd=api_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
    finally:
        if application is not None:
            application.state.engine.dispose()
        if created:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
            )
        admin.close()
