import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import select
from sqlalchemy.engine import make_url


@pytest.fixture
def postgres_app(tmp_path):
    if not os.getenv("TEST_POSTGRES_ADMIN_URL"):
        pytest.skip("Isolated PostgreSQL admin URL not supplied")
    from app.core.config import Settings
    from app.main import create_app

    base = make_url(os.environ["TEST_POSTGRES_ADMIN_URL"])
    name = "devdocs_chat_test_" + uuid4().hex[:12]
    admin = psycopg.connect(
        base.set(drivername="postgresql", database="postgres").render_as_string(
            hide_password=False
        ),
        autocommit=True,
    )
    url = base.set(database=name).render_as_string(hide_password=False)
    app = None
    created = False

    def migrate(*args):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "DATABASE_URL": url, "SILICONFLOW_API_KEY": ""},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr

    try:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        created = True
        migrate("upgrade", "0005_document_chunks")
        migrate("upgrade", "head")
        migrate("check")
        app = create_app(
            Settings(database_url=url, siliconflow_api_key=None, upload_dir=tmp_path / "uploads")
        )
        yield app, migrate
    finally:
        if app:
            app.state.engine.dispose()
        if created:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.close()


def test_real_pgvector_scope_sort_migration_and_cascade(postgres_app):
    from app.models.chunk import DocumentChunk
    from app.models.conversation import Conversation
    from app.models.document import Document
    from app.models.message import Message
    from app.models.user import User
    from app.rag.retriever import retrieve_sources
    from app.services.indexing_service import fingerprint

    app, migrate = postgres_app
    with TestClient(app) as client:
        client.post(
            "/auth/register", json={"email": "pg-chat@example.com", "password": "Study-safe-2026!"}
        )
        kb = client.post("/knowledge-bases", json={"name": "PG Chat"}).json()["id"]
        kb2 = client.post("/knowledge-bases", json={"name": "Other"}).json()["id"]
        identifier = client.post(f"/knowledge-bases/{kb}/conversations", json={}).json()["id"]
        with app.state.session_factory() as db:
            user = db.scalar(select(User))
            for index, (library, status, score, old) in enumerate(
                [
                    (kb, "completed", 1.0, False),
                    (kb, "completed", 0.6, False),
                    (kb2, "completed", 1.0, False),
                    (kb, "failed", 1.0, False),
                    (kb, "completed", 1.0, True),
                    (kb, "completed", 0.2, False),
                ]
            ):
                doc = Document(
                    user_id=user.id,
                    knowledge_base_id=UUID(library),
                    filename=f"{index}.txt",
                    file_type="txt",
                    size_bytes=10,
                    content_hash=str(index) * 64,
                    storage_key=str(uuid4()),
                    status="parsed",
                    extracted_text="text",
                    index_status=status,
                    index_fingerprint="old" if old else fingerprint(str(index) * 64),
                    chunk_count=1,
                )
                db.add(doc)
                db.flush()
                vector = [score, (1 - score**2) ** 0.5] + [0.0] * 1022
                db.add(
                    DocumentChunk(
                        user_id=user.id,
                        knowledge_base_id=UUID(library),
                        document_id=doc.id,
                        chunk_index=0,
                        content="source",
                        source_metadata={"page": 1},
                        embedding_model="BAAI/bge-m3",
                        embedding_dimension=1024,
                        embedding=vector,
                    )
                )
            db.commit()
            result = retrieve_sources(
                db, user.id, UUID(kb), [1.0] + [0.0] * 1023, app.state.settings
            )
            assert [source.filename for source in result] == ["0.txt", "1.txt"]
            assert result[0].similarity == pytest.approx(1.0)
            db.add(
                Message(
                    conversation_id=UUID(identifier),
                    sequence=1,
                    role="assistant",
                    content="x",
                    status="completed",
                )
            )
            db.commit()
        history = client.get(f"/knowledge-bases/{kb}/conversations").json()
        assert history["total"] == 0  # Assistant-only legacy rows have no user question/title.
        with app.state.session_factory() as db:
            db.add(
                Message(
                    conversation_id=UUID(identifier),
                    sequence=2,
                    role="user",
                    content="PG history question",
                    status="completed",
                )
            )
            db.commit()
        history = client.get(f"/knowledge-bases/{kb}/conversations").json()
        assert history["items"][0]["title"] == "PG history question"
        assert (
            client.get(f"/conversations/{identifier}?before_sequence=2&limit=1").json()["messages"][
                0
            ]["sequence"]
            == 1
        )
        # Deletion must wait for the conversation before taking message locks.
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event

        from sqlalchemy import event, text, update

        reached = Event()

        def before(connection, cursor, statement, parameters, context, many):
            if statement.startswith("SELECT conversations.") and "FOR UPDATE" in statement:
                reached.set()

        def after(connection, cursor, statement, parameters, context, many):
            if statement.startswith("DELETE FROM messages"):
                reached.set()

        with app.state.session_factory() as held:
            held.scalar(
                select(Conversation).where(Conversation.id == UUID(identifier)).with_for_update()
            )
            held.execute(text("SET LOCAL lock_timeout = '1500ms'"))
            event.listen(app.state.engine, "before_cursor_execute", before)
            event.listen(app.state.engine, "after_cursor_execute", after)
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(client.delete, f"/knowledge-bases/{kb}")
                    try:
                        assert reached.wait(5)
                        held.execute(
                            update(Message)
                            .where(Message.conversation_id == UUID(identifier))
                            .values(content="finished")
                        )
                        held.commit()
                    finally:
                        held.rollback()
                    assert future.result(timeout=5).status_code == 204
            finally:
                event.remove(app.state.engine, "before_cursor_execute", before)
                event.remove(app.state.engine, "after_cursor_execute", after)
        with app.state.session_factory() as db:
            assert db.get(Conversation, UUID(identifier)) is None
            assert db.scalar(select(Message)) is None
    migrate("downgrade", "0005_document_chunks")
    with app.state.engine.connect() as connection:
        from sqlalchemy import text

        assert connection.scalar(text("SELECT to_regclass('public.messages')")) is None
        assert connection.scalar(text("SELECT count(*) FROM documents")) == 1
    migrate("upgrade", "head")
