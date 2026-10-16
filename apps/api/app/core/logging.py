import json
import logging
import time
from contextvars import ContextVar
from uuid import uuid4

from starlette.responses import JSONResponse

request_id_context = ContextVar("request_id", default=None)
FIELDS = {
    "request_id",
    "user_id",
    "document_id",
    "knowledge_base_id",
    "run_id",
    "operation",
    "status",
    "route",
    "duration_ms",
    "error_code",
    "error_type",
    "model",
    "phase",
    "chunks",
}
EVENTS = {
    "http_started",
    "http_finished",
    "request_failed",
    "chat_finished",
    "index_finished",
    "document_parsed",
    "storage_failed",
    "cleanup_deferred",
    "database_failed",
    "usage_storage_failed",
    "cancel_storage_failed",
}


def safe_log(logger, event, **fields):
    payload = {
        key: value
        for key, value in fields.items()
        if key in FIELDS and isinstance(value, (str, int, float, type(None)))
    }
    payload["event"] = event if event in EVENTS else "request_failed"
    payload.setdefault("request_id", request_id_context.get())
    logger.info(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))


class SafeFormatter(logging.Formatter):
    def format(self, record):
        try:
            value = (
                json.loads(record.msg) if not record.args and isinstance(record.msg, str) else None
            )
        except (ValueError, TypeError):
            value = None
        if not isinstance(value, dict) or value.get("event") not in EVENTS:
            value = {"event": "request_failed", "request_id": request_id_context.get()}
        return json.dumps(
            {k: v for k, v in value.items() if k in FIELDS or k == "event"}, ensure_ascii=True
        )


def configure_logging():
    logger = logging.getLogger("app")
    if not any(getattr(handler, "devdocs_safe", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.devdocs_safe = True
        handler.setFormatter(SafeFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        identifier = str(uuid4())
        scope.setdefault("state", {})["request_id"] = identifier
        token = request_id_context.set(identifier)
        started, response_started, status = time.monotonic(), False, 500
        logger = logging.getLogger("app.http")

        def fields():
            route = scope.get("route")
            return {
                "request_id": identifier,
                "route": getattr(route, "path", "unmatched"),
                "status": status,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }

        async def wrapped(message):
            nonlocal response_started, status
            if message["type"] == "http.response.start":
                response_started, status = True, message["status"]
                message["headers"] = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ] + [(b"x-request-id", identifier.encode())]
                safe_log(logger, "http_started", **fields())
            await send(message)

        try:
            await self.app(scope, receive, wrapped)
        except Exception as error:
            safe_log(
                logger,
                "request_failed",
                **fields(),
                error_type=type(error).__name__,
                error_code="internal_error",
            )
            if not response_started:
                await JSONResponse(
                    {"detail": "服务暂不可用，请稍后重试", "request_id": identifier},
                    status_code=500,
                )(scope, receive, wrapped)
            else:
                await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            safe_log(logger, "http_finished", **fields())
            request_id_context.reset(token)
