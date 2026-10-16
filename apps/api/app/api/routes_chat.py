import asyncio
from uuid import UUID

import anyio
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, Database
from app.schemas.chat import CancelRequest, ChatRequest
from app.services.chat_service import cancel_chat_run, claim_chat_run, stream_chat

router = APIRouter(tags=["chat"])


@router.post("/conversations/{conversation_id}/chat/stream")
async def chat(
    conversation_id: UUID, data: ChatRequest, request: Request, user: CurrentUser, db: Database
):
    factory, settings = request.app.state.session_factory, request.app.state.settings
    runtime = request.app.state.chat_runtime
    user_id = user.id
    db.close()
    runtime.reserve(data.request_id, asyncio.get_running_loop())

    def claim():
        with factory() as session:
            return claim_chat_run(
                session,
                user_id,
                conversation_id,
                data.question,
                data.request_id,
                settings,
                trace_id=getattr(request.state, "request_id", None),
            )

    try:
        run = await anyio.to_thread.run_sync(claim)
    except BaseException:
        runtime.release(data.request_id)
        raise
    return StreamingResponse(
        stream_chat(run, factory, settings, runtime),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations/{conversation_id}/chat/cancel", status_code=204)
async def cancel(
    conversation_id: UUID, data: CancelRequest, request: Request, user: CurrentUser, db: Database
):
    user_id = user.id
    db.close()

    def cancel_owned():
        with request.app.state.session_factory() as session:
            cancel_chat_run(
                session, user_id, conversation_id, data.run_id, request.app.state.chat_runtime
            )

    await anyio.to_thread.run_sync(cancel_owned)
    return Response(status_code=204)
