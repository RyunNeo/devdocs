import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from test_chat import client as chat_client
from test_chat import frames, setup


@pytest.fixture
def client(tmp_path, monkeypatch):
    yield from chat_client.__wrapped__(tmp_path, monkeypatch)


def test_cancel_before_producer_starts_is_saved(client):
    from app.models.message import Message
    from app.services.chat_service import claim_chat_run, stream_chat

    _, identifier, _ = setup(client)
    application = client.app
    with application.state.session_factory() as db:
        from app.models.conversation import Conversation

        user_id = db.get(Conversation, UUID(identifier)).user_id
        run = claim_chat_run(
            db, user_id, UUID(identifier), "问题", uuid4(), application.state.settings
        )

    async def stop_immediately():
        runtime = application.state.chat_runtime
        runtime.reserve(run.run_id, asyncio.get_running_loop())
        runtime.cancel(run.run_id)
        stream = stream_chat(
            run, application.state.session_factory, application.state.settings, runtime
        )
        await anext(stream)
        await stream.aclose()

    asyncio.run(stop_immediately())
    with application.state.session_factory() as db:
        assert db.get(Message, run.assistant_message_id).status == "cancelled"


def test_stop_discards_draft_and_releases_lease(client, monkeypatch):
    from app.rag import chat_model
    from app.rag.chat_model import ProviderEvent

    started = Event()

    class Slow:
        async def astream(self, messages, deadline):
            yield ProviderEvent("token", {"delta": "部分正文"})
            started.set()
            await asyncio.sleep(30)

    monkeypatch.setattr(chat_model, "make_chat_model", lambda settings: Slow())
    _, identifier, _ = setup(client)
    run_id = str(uuid4())
    payload = {"question": "问题", "request_id": run_id}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, f"/conversations/{identifier}/chat/stream", json=payload)
        assert started.wait(5)
        assert (
            client.post(
                f"/conversations/{identifier}/chat/stream",
                json={"question": "重复", "request_id": str(uuid4())},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/conversations/{identifier}/chat/cancel", json={"run_id": run_id}
            ).status_code
            == 204
        )
        assert frames(future.result(timeout=15))[-1][0] == "error"
    answer = client.get(f"/conversations/{identifier}").json()["messages"][-1]
    assert answer["status"] == "cancelled" and answer["content"] == ""
    assert not client.app.state.chat_runtime.runs


def test_expired_lease_is_recovered(client):
    from app.models.conversation import Conversation
    from app.models.message import Message

    _, identifier, _ = setup(client, indexed=False)
    with client.app.state.session_factory() as db:
        conversation = db.get(Conversation, UUID(identifier))
        conversation.active_run_id = uuid4()
        conversation.active_started_at = datetime.now(timezone.utc) - timedelta(seconds=181)
        db.add(
            Message(
                conversation_id=conversation.id,
                run_id=conversation.active_run_id,
                sequence=1,
                role="assistant",
                content="",
                status="streaming",
            )
        )
        db.commit()
    detail = client.get(f"/conversations/{identifier}").json()
    assert detail["messages"][0]["status"] == "failed"
    assert detail["messages"][0]["error_code"] == "interrupted"


def test_deleted_library_cannot_be_resurrected(client, monkeypatch):
    from app.models.message import Message
    from app.rag import chat_model
    from app.rag.chat_model import ProviderEvent

    kb, identifier, _ = setup(client)

    class Delete:
        async def astream(self, messages, deadline):
            response = await asyncio.to_thread(client.delete, f"/knowledge-bases/{kb}")
            assert response.status_code == 204
            yield ProviderEvent("token", {"delta": "答案 [1]"})
            yield ProviderEvent("finish", {"finish_reason": "stop"})

    monkeypatch.setattr(chat_model, "make_chat_model", lambda settings: Delete())
    client.post(
        f"/conversations/{identifier}/chat/stream",
        json={"question": "问题", "request_id": str(uuid4())},
    )
    assert client.get(f"/conversations/{identifier}").status_code == 404
    with client.app.state.session_factory() as db:
        assert not list(db.scalars(select(Message)))


def test_cancel_database_work_does_not_block_event_loop(client, monkeypatch):
    import time

    from app.api import routes_chat

    _, identifier, _ = setup(client, indexed=False)
    original = routes_chat.cancel_chat_run
    started = Event()

    def slow(*args):
        started.set()
        time.sleep(1)
        return original(*args)

    monkeypatch.setattr(routes_chat, "cancel_chat_run", slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            client.post, f"/conversations/{identifier}/chat/cancel", json={"run_id": str(uuid4())}
        )
        assert started.wait(3)
        now = time.monotonic()
        assert client.get("/health").status_code == 200
        elapsed = time.monotonic() - now
        assert future.result(timeout=3).status_code == 204
    assert elapsed < 0.5


def test_repeated_cancel_does_not_interrupt_terminal_save():
    from app.services.chat_service import ChatRun, ChatRuntime

    async def run():
        runtime = ChatRuntime()
        run_id = uuid4()
        runtime.reserve(run_id, asyncio.get_running_loop())
        saving = asyncio.Event()
        saved = asyncio.Event()

        async def worker():
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                saving.set()
                await asyncio.sleep(0.03)
                saved.set()

        task = asyncio.create_task(worker())
        runtime.attach(ChatRun(run_id, uuid4(), uuid4(), uuid4(), uuid4(), "q", 1), task)
        await asyncio.sleep(0)
        runtime.cancel(run_id)
        await saving.wait()
        runtime.cancel(run_id)
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert saved.is_set()

    asyncio.run(run())
