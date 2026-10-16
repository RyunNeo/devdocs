import asyncio
from uuid import UUID, uuid4

import pytest
from test_chat import client as base_client
from test_chat import frames, setup


@pytest.fixture
def client(tmp_path, monkeypatch):
    yield from base_client.__wrapped__(tmp_path, monkeypatch)


def test_no_tokens_leave_before_validation_and_save(client, monkeypatch):
    from app.models.conversation import Conversation
    from app.models.message import Message
    from app.rag import chat_model
    from app.rag.chat_model import ProviderEvent
    from app.services.chat_service import claim_chat_run, stream_chat

    _, identifier, _ = setup(client)
    app = client.app

    async def run_test():
        started, release = asyncio.Event(), asyncio.Event()

        class Slow:
            async def astream(self, messages, deadline):
                yield ProviderEvent("token", {"delta": "答案 [1]"})
                started.set()
                await release.wait()
                yield ProviderEvent("finish", {"finish_reason": "stop"})

        monkeypatch.setattr(chat_model, "make_chat_model", lambda settings: Slow())
        with app.state.session_factory() as db:
            user_id = db.get(Conversation, UUID(identifier)).user_id
            run = claim_chat_run(db, user_id, UUID(identifier), "问题", uuid4(), app.state.settings)
        runtime = app.state.chat_runtime
        runtime.reserve(run.run_id, asyncio.get_running_loop())
        stream = stream_chat(run, app.state.session_factory, app.state.settings, runtime)
        collected = []
        try:
            while not started.is_set():
                frame = await anext(stream)
                collected.append(frame)
                assert b"event: token" not in frame
                await asyncio.sleep(0)
            release.set()
            async for frame in stream:
                if b"event: token" in frame:
                    with app.state.session_factory() as db:
                        assert db.get(Message, run.assistant_message_id).status == "completed"
                collected.append(frame)
        finally:
            release.set()
            await stream.aclose()
        assert b"event: status" in b"".join(collected)

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "body,expected",
    [("推测 [1] [[INSUFFICIENT_EVIDENCE]]", "refusal"), ("不支持的结论 [99]", "failed")],
)
def test_unvalidated_body_is_never_published(client, monkeypatch, body, expected):
    from app.rag import chat_model
    from app.rag.chat_model import ProviderEvent
    from app.rag.citations import INSUFFICIENT

    class Generated:
        async def astream(self, messages, deadline):
            yield ProviderEvent("token", {"delta": body})
            yield ProviderEvent("finish", {"finish_reason": "stop"})

    monkeypatch.setattr(chat_model, "make_chat_model", lambda settings: Generated())
    _, identifier, _ = setup(client)
    response = client.post(
        f"/conversations/{identifier}/chat/stream",
        json={"question": "问题", "request_id": str(uuid4())},
    )
    events = frames(response)
    tokens = "".join(data["delta"] for name, data in events if name == "token")
    assert tokens == (INSUFFICIENT if expected == "refusal" else "")
    saved = client.get(f"/conversations/{identifier}").json()["messages"][-1]
    assert saved["content"] == (INSUFFICIENT if expected == "refusal" else "")
