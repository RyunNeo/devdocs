import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import anyio
from fastapi import HTTPException
from sqlalchemy import func, select, update

from app.core.logging import safe_log
from app.core.usage_context import UsageMetrics, UsageRecorder, bind_usage
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.usage import UsageEvent
from app.rag import chain, chat_model
from app.rag.chat_model import ChatModelError
from app.rag.citations import INSUFFICIENT, CitationError, ValidatedAnswer, validate_answer
from app.rag.prompts import build_prompt_messages
from app.rag.stream_protocol import encode_sse
from app.services.conversation_service import (
    expire_run,
    get_owned_conversation,
    refresh_citation_status,
)
from app.services.usage_service import finish_operation, reserve_operation

logger = logging.getLogger(__name__)


@dataclass
class ChatRun:
    run_id: UUID
    conversation_id: UUID
    assistant_message_id: UUID
    knowledge_base_id: UUID
    user_id: UUID
    question: str
    user_sequence: int
    usage_event_id: UUID | None = None
    request_id: str | None = None


class ChatRuntime:
    def __init__(self):
        self.lock = threading.Lock()
        self.runs = {}

    def reserve(self, run_id, loop):
        with self.lock:
            if run_id in self.runs:
                raise HTTPException(409, "这个请求已提交，请刷新会话查看结果")
            if len(self.runs) >= 2:
                raise HTTPException(429, "回答任务较多，请稍后再试")
            self.runs[run_id] = {"loop": loop, "task": None, "kb": None, "cancelled": False}

    def attach(self, run, task):
        with self.lock:
            entry = self.runs.get(run.run_id)
            if entry:
                entry.update(task=task, kb=run.knowledge_base_id)
                if entry["cancelled"]:
                    entry["loop"].call_soon(self.cancel_task, task)

    @staticmethod
    def cancel_task(task):
        if not task.done() and not task.cancelling():
            task.cancel()

    def cancel(self, run_id):
        with self.lock:
            entry = self.runs.get(run_id)
            if entry and not entry["cancelled"]:
                entry["cancelled"] = True
                if entry["task"]:
                    entry["loop"].call_soon_threadsafe(self.cancel_task, entry["task"])

    def cancel_kb(self, kb_id):
        with self.lock:
            identifiers = [rid for rid, entry in self.runs.items() if entry["kb"] == kb_id]
        for identifier in identifiers:
            self.cancel(identifier)

    def release(self, run_id):
        with self.lock:
            self.runs.pop(run_id, None)


def claim_chat_run(db, user_id, conversation_id, question, request_id, settings, trace_id=None):
    conversation = get_owned_conversation(db, user_id, conversation_id, lock=True)
    expire_run(db, conversation)
    if conversation.active_run_id:
        raise HTTPException(409, "当前会话正在回答，请先停止或等待完成")
    if db.scalar(
        select(Message.id).where(
            Message.conversation_id == conversation_id, Message.run_id == request_id
        )
    ):
        raise HTTPException(409, "这个请求已提交，请刷新会话查看结果")
    # Empty libraries can return a local no-evidence answer without a provider key.
    from app.rag.retriever import has_sources

    if has_sources(db, user_id, conversation.knowledge_base_id):
        key = settings.siliconflow_api_key
        if key is None or not key.get_secret_value().strip():
            raise HTTPException(503, "请先配置 SILICONFLOW_API_KEY")
    now = datetime.now(timezone.utc)
    event = reserve_operation(
        db,
        user_id,
        "chat",
        request_id,
        trace_id or str(request_id),
        settings,
        knowledge_base_id=conversation.knowledge_base_id,
        conversation_id=conversation_id,
        now=now,
    )
    db.flush()
    claimed = db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id, Conversation.active_run_id.is_(None))
        .values(active_run_id=request_id, active_started_at=now, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        raise HTTPException(409, "当前会话正在回答")
    sequence = (
        db.scalar(
            select(func.max(Message.sequence)).where(Message.conversation_id == conversation_id)
        )
        or 0
    ) + 1
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=question,
        status="completed",
        run_id=request_id,
        sequence=sequence,
    )
    assistant = Message(
        conversation_id=conversation_id,
        role="assistant",
        content="",
        status="streaming",
        run_id=request_id,
        sequence=sequence + 1,
        model=settings.chat_model,
    )
    db.add_all([user_message, assistant])
    db.commit()
    return ChatRun(
        request_id,
        conversation_id,
        assistant.id,
        conversation.knowledge_base_id,
        user_id,
        question,
        sequence,
        event.id,
        event.request_id,
    )


def finish_run(factory, run, status, content, citations, usage=None, error_code=None):
    if status != "completed":
        content, citations = "", []
    with factory() as db:
        conversation = db.scalar(
            select(Conversation)
            .where(Conversation.id == run.conversation_id, Conversation.user_id == run.user_id)
            .with_for_update()
        )
        if conversation is None or conversation.active_run_id != run.run_id:
            return False
        citations[:] = refresh_citation_status(db, run.user_id, citations)
        now = datetime.now(timezone.utc)
        changed = db.execute(
            update(Message)
            .where(
                Message.id == run.assistant_message_id,
                Message.run_id == run.run_id,
                Message.status == "streaming",
            )
            .values(
                status=status,
                content=content,
                citations=citations,
                usage=usage,
                error_code=error_code,
                updated_at=now,
            )
        )
        conversation.active_run_id = None
        conversation.active_started_at = None
        conversation.updated_at = now
        db.commit()
        return changed.rowcount == 1


def cancel_chat_run(db, user_id, conversation_id, run_id, runtime):
    conversation = get_owned_conversation(db, user_id, conversation_id, lock=True)
    if conversation.active_run_id == run_id:
        runtime.cancel(run_id)
        # Other-worker cancellation invalidates the lease without retaining a draft.
        with runtime.lock:
            local = run_id in runtime.runs
        if not local:
            db.execute(
                update(UsageEvent)
                .where(
                    UsageEvent.operation == "chat",
                    UsageEvent.operation_run_id == run_id,
                    UsageEvent.user_id == user_id,
                    UsageEvent.status == "running",
                )
                .values(
                    status="cancelled",
                    error_code="cancelled",
                    finished_at=datetime.now(timezone.utc),
                )
            )
            db.execute(
                update(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.run_id == run_id,
                    Message.status == "streaming",
                )
                .values(
                    status="cancelled",
                    content="",
                    citations=[],
                    error_code="cancelled",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            conversation.active_run_id = None
            conversation.active_started_at = None
    db.commit()


async def stream_chat(run, session_factory, settings, runtime):
    queue = asyncio.Queue(maxsize=32)
    content = ""
    usage = None
    persisted = False
    started = time.monotonic()
    recorder = UsageRecorder(session_factory, run.usage_event_id) if run.usage_event_id else None

    async def save(status, text, citations, code=None):
        return await anyio.to_thread.run_sync(
            finish_run, session_factory, run, status, text, citations, usage, code
        )

    async def produce():
        nonlocal content, usage, persisted
        code = None
        outcome = "failed"
        scope = bind_usage(recorder)
        scope.__enter__()
        try:
            async with asyncio.timeout(settings.chat_timeout_seconds):
                await queue.put(encode_sse("status", {"phase": "retrieving"}))
                from contextlib import nullcontext

                with recorder.stage("retrieval") if recorder else nullcontext():
                    history, available = await anyio.to_thread.run_sync(
                        chain.prepare_context, session_factory, run
                    )
                    sources = []
                    if available:
                        with recorder.stage("query_embedding") if recorder else nullcontext():
                            vector = await chain.embed_question(settings, run.question, history)
                        sources = await anyio.to_thread.run_sync(
                            chain.query_context, session_factory, run, vector, settings
                        )
                if not sources:
                    content = INSUFFICIENT
                    answer = ValidatedAnswer(content, [], True)
                else:
                    await queue.put(encode_sse("status", {"phase": "generating"}))
                    finished = False
                    model_started = time.monotonic()
                    async for event in chat_model.make_chat_model(settings).astream(
                        build_prompt_messages(run.question, history, sources),
                        started + settings.chat_timeout_seconds,
                    ):
                        if event.kind == "token":
                            content += event.data["delta"]
                            if len(content.encode()) > 1024 * 1024:
                                raise ChatModelError("stream_limit", "回答超过大小限制")
                        elif event.kind == "usage":
                            usage = event.data
                            if recorder:
                                recorder.observe_tokens("chat", usage)
                        elif event.kind == "finish":
                            finished = True
                    if not finished:
                        raise ChatModelError("interrupted", "回答流已中断")
                    if recorder:
                        recorder.metrics.durations_ms["chat"] = round(
                            (time.monotonic() - model_started) * 1000
                        )
                    await queue.put(encode_sse("status", {"phase": "validating"}))
                    with recorder.stage("validation") if recorder else nullcontext():
                        answer = validate_answer(content, sources)
                if not sources:
                    await queue.put(encode_sse("status", {"phase": "validating"}))
                persisted = await save("completed", answer.content, answer.citations)
                if not persisted:
                    raise ChatModelError("run_expired", "会话或任务已失效，请刷新")
                attempted = recorder and any(recorder.metrics.attempts.values())
                outcome = "completed" if sources or attempted else "local_completed"
                for offset in range(0, len(answer.content), 8000):
                    await queue.put(
                        encode_sse("token", {"delta": answer.content[offset : offset + 8000]})
                    )
                await queue.put(encode_sse("citations", {"items": answer.citations}))
                await queue.put(
                    encode_sse(
                        "done",
                        {
                            "message_id": str(run.assistant_message_id),
                            "status": "completed",
                            "finish_reason": "stop",
                            "usage": usage,
                            **({"content": answer.content} if answer.insufficient else {}),
                        },
                    )
                )
        except asyncio.CancelledError:
            code = "cancelled"
            if not persisted:
                outcome = "cancelled"
            with anyio.CancelScope(shield=True):
                if not persisted:
                    try:
                        await save("cancelled", content, [], code)
                    except Exception:
                        code = "storage_failed"
            # A stopped browser may no longer consume the queue.
            try:
                queue.put_nowait(
                    encode_sse(
                        "error",
                        {
                            "code": code,
                            "message": "已停止生成",
                            "message_id": str(run.assistant_message_id),
                        },
                    )
                )
            except asyncio.QueueFull:
                pass
        except Exception as error:
            code = (
                "citation_invalid"
                if isinstance(error, CitationError)
                else error.code
                if isinstance(error, ChatModelError)
                else "timeout"
                if isinstance(error, TimeoutError)
                else "answer_failed"
            )
            message = (
                str(error)
                if isinstance(error, (CitationError, ChatModelError))
                else "回答失败，请刷新会话查看结果"
            )
            with anyio.CancelScope(shield=True):
                try:
                    if not persisted:
                        await save("failed", content, [], code)
                except Exception:
                    code, message = "storage_failed", "回答保存失败，请刷新会话确认"
            await queue.put(
                encode_sse(
                    "error",
                    {"code": code, "message": message, "message_id": str(run.assistant_message_id)},
                )
            )
        finally:
            if recorder:
                recorder.metrics.durations_ms["total"] = round((time.monotonic() - started) * 1000)
                with anyio.CancelScope(shield=True):
                    try:
                        await anyio.to_thread.run_sync(
                            finish_operation,
                            session_factory,
                            run.usage_event_id,
                            outcome,
                            recorder.snapshot(),
                            code,
                        )
                    except Exception:
                        safe_log(
                            logger,
                            "usage_storage_failed",
                            request_id=run.request_id,
                            run_id=str(run.run_id),
                        )
            scope.__exit__(None, None, None)
            safe_log(
                logger,
                "chat_finished",
                request_id=run.request_id,
                run_id=str(run.run_id),
                model=settings.chat_model,
                duration_ms=round((time.monotonic() - started) * 1000),
                error_code=code,
                status=outcome,
            )
            runtime.release(run.run_id)

    task = asyncio.create_task(produce())

    def wake_consumer(_):
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

    task.add_done_callback(wake_consumer)
    runtime.attach(run, task)
    try:
        yield encode_sse(
            "meta",
            {
                "conversation_id": str(run.conversation_id),
                "run_id": str(run.run_id),
                "assistant_message_id": str(run.assistant_message_id),
                "user_sequence": run.user_sequence,
            },
        )
        while not task.done() or not queue.empty():
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=10)
                if frame is None:
                    break
                yield frame
            except TimeoutError:
                if not task.done():
                    yield b": heartbeat\n\n"
    finally:
        runtime.cancel_task(task)
        with anyio.CancelScope(shield=True):
            try:
                await task
            except asyncio.CancelledError:
                # Cancellation before the producer's first await still needs a saved terminal state.
                try:
                    await save("cancelled", content, [], "cancelled")
                    if run.usage_event_id:
                        await anyio.to_thread.run_sync(
                            finish_operation,
                            session_factory,
                            run.usage_event_id,
                            "cancelled",
                            UsageMetrics(),
                            "cancelled",
                        )
                except Exception:
                    safe_log(
                        logger,
                        "cancel_storage_failed",
                        request_id=run.request_id,
                        run_id=str(run.run_id),
                    )
        runtime.release(run.run_id)
