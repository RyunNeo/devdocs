import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_chat import router as chat_router
from app.api.routes_conversations import router as conversation_router
from app.api.routes_documents import router as document_router
from app.api.routes_knowledge_bases import router as knowledge_base_router
from app.api.routes_usage import router as usage_router
from app.core.config import Settings
from app.core.logging import RequestLoggingMiddleware, configure_logging, safe_log
from app.db.session import make_database
from app.services.chat_service import ChatRuntime

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or Settings()
    engine, session_factory = make_database(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        engine.dispose()

    application = FastAPI(title="DevDocs AI API", version="0.1.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.chat_runtime = ChatRuntime()
    application.add_middleware(
        RequestBodyLimitMiddleware, max_body_size=settings.max_upload_bytes + 64 * 1024
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @application.middleware("http")
    async def check_origin(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin not in settings.allowed_origins:
                return JSONResponse({"detail": "请求来源未获允许"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        # Default validation details can echo passwords supplied by the user.
        errors = [{"loc": list(item["loc"]), "type": item["type"]} for item in error.errors()]
        return JSONResponse({"detail": "请检查请求参数格式", "errors": errors}, status_code=422)

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        safe_log(logger, "database_failed", error_type=type(error).__name__)
        return JSONResponse(
            {"detail": "数据库暂不可用，请检查数据库启动状态和迁移"}, status_code=503
        )

    @application.exception_handler(StarletteHTTPException)
    async def safe_http_error(request: Request, error: StarletteHTTPException):
        payload = {"detail": error.detail}
        if error.headers and error.headers.get("X-Error-Code") == "daily_quota_exceeded":
            payload.update(
                code="daily_quota_exceeded",
                operation=error.headers.get("X-Quota-Operation"),
                reset_at=error.headers.get("X-Quota-Reset-At"),
            )
        return JSONResponse(payload, status_code=error.status_code, headers=error.headers)

    @application.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    @application.get("/health/ready", tags=["health"])
    def ready():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if engine.dialect.name == "postgresql":
                version = connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
                if version is None:
                    return JSONResponse(
                        {"status": "not_ready", "detail": "pgvector 扩展尚未安装"}, status_code=503
                    )
            else:
                version = None
            connection.execute(text("SELECT id FROM users LIMIT 1"))
            connection.execute(text("SELECT token_hash FROM auth_sessions LIMIT 1"))
            connection.execute(text("SELECT id FROM knowledge_bases LIMIT 1"))
            connection.execute(text("SELECT id FROM documents LIMIT 1"))
            connection.execute(text("SELECT storage_key FROM storage_cleanup_tasks LIMIT 1"))
            connection.execute(text("SELECT id FROM document_chunks LIMIT 1"))
            connection.execute(text("SELECT index_status, parse_warning FROM documents LIMIT 1"))
            connection.execute(text("SELECT id FROM conversations LIMIT 1"))
            connection.execute(text("SELECT id FROM messages LIMIT 1"))
            connection.execute(text("SELECT id FROM usage_events LIMIT 1"))
            connection.execute(text("SELECT used_count FROM daily_usage_counters LIMIT 1"))
        return {"status": "ready", "database": engine.dialect.name, "pgvector": version}

    application.include_router(auth_router)
    application.include_router(conversation_router)
    application.include_router(chat_router)
    application.include_router(knowledge_base_router)
    application.include_router(document_router)
    application.include_router(usage_router)
    application.add_middleware(RequestLoggingMiddleware)
    return application


app = create_app()
