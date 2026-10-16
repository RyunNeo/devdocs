import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from evals.toolkit.sse import LineDecoder, SSEDecoder

STREAM_TIMEOUT_SECONDS = 180


class EvaluationError(ValueError):
    def __init__(self, code: str, status: int | None = None, request_id: str | None = None):
        self.code, self.status, self.request_id = code, status, request_id
        hints = {
            "preparation_incomplete": "资料准备未完成，不能运行问答；请先检查 prepare 的失败原因。",
            "knowledge_base_name_conflict": (
                "已有同名测试知识库，请使用新的运行编号 --run-id；不会自动复用或删除已有知识库。"
            ),
        }
        message = f"{code}" + (f" (HTTP {status})" if status else "")
        super().__init__(message + (f"：{hints[code]}" if code in hints else ""))


@dataclass
class StreamResult:
    meta: dict = field(default_factory=dict)
    answer: str = ""
    citations: list[dict] = field(default_factory=list)
    done: dict = field(default_factory=dict)
    elapsed_ms: int | None = None


def normalize_url(url: str, allow_remote: bool = False) -> str:
    parsed = urlsplit(url)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (not local and (not allow_remote or parsed.scheme != "https"))
    ):
        raise ValueError("基础地址仅允许本机 HTTP(S)，远程需 HTTPS 与 --allow-remote")
    return str(httpx.URL(url)).rstrip("/")


def resource_id(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", str(value)):
        raise EvaluationError("invalid_resource_id")
    return str(value)


class EvaluationClient:
    def __init__(self, base_url: str, *, allow_remote: bool = False, transport=None):
        self.base_url = normalize_url(base_url, allow_remote)
        self.transport = transport
        self.http = httpx.Client(
            base_url=self.base_url,
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(30, connect=10),
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def _check(self, response):
        if not 200 <= response.status_code < 300:
            codes = {401: "login_required", 429: "quota_or_rate_limit", 403: "forbidden"}
            trace = response.headers.get("x-request-id", "")
            raise EvaluationError(
                codes.get(response.status_code, "http_error"),
                response.status_code,
                trace if re.fullmatch(r"[a-fA-F0-9-]{36}", trace) else None,
            )

    def _json(self, method, path, **kwargs):
        try:
            response = self.http.request(method, path, **kwargs)
            self._check(response)
            data = response.json()
            if not isinstance(data, dict):
                raise EvaluationError("invalid_response")
            return data
        except httpx.HTTPError:
            raise EvaluationError("network_error") from None
        except (ValueError, TypeError) as exc:
            if isinstance(exc, EvaluationError):
                raise
            raise EvaluationError("invalid_response") from None

    def login(self, email, password):
        return self._json("POST", "/auth/login", json={"email": email, "password": password})

    def me(self):
        return self._json("GET", "/auth/me")

    def summary(self):
        return self._json("GET", "/usage/summary")

    def create_kb(self, name):
        try:
            return self._json("POST", "/knowledge-bases", json={"name": name})
        except EvaluationError as exc:
            if exc.status == 409:
                raise EvaluationError("knowledge_base_name_conflict", 409, exc.request_id) from None
            raise

    def upload(self, kb_id, path: Path):
        with path.open("rb") as file:
            return self._json(
                "POST",
                f"/knowledge-bases/{resource_id(kb_id)}/documents",
                files={"file": (path.name, file, "text/markdown")},
            )

    def index(self, doc_id):
        data = self._json(
            "POST",
            f"/documents/{resource_id(doc_id)}/index",
            timeout=httpx.Timeout(180, connect=10),
        )
        if data.get("index_status") != "completed":
            raise EvaluationError("index_failed")
        return data

    def list_documents(self, kb_id):
        items = []
        for _ in range(100):
            page = self._json(
                "GET",
                f"/knowledge-bases/{resource_id(kb_id)}/documents",
                params={"limit": 100, "offset": len(items)},
            )
            batch = page.get("items")
            if not isinstance(batch, list) or not isinstance(page.get("total"), int):
                raise EvaluationError("invalid_response")
            items.extend(batch)
            if len(items) >= page["total"]:
                return items
            if not batch:
                break
        raise EvaluationError("invalid_pagination")

    def create_conversation(self, kb_id):
        return self._json("POST", f"/knowledge-bases/{resource_id(kb_id)}/conversations", json={})

    def read_conversation(self, conversation_id):
        return self._json(
            "GET", f"/conversations/{resource_id(conversation_id)}", params={"limit": 100}
        )

    def stream_answer(self, conversation_id, question, request_id):
        return asyncio.run(self._stream_answer(conversation_id, question, request_id))

    def _consume_event(self, result, event):
        if event is None:
            return
        if event.event == "meta":
            result.meta = event.data
        elif event.event == "token":
            delta = event.data.get("delta")
            if not isinstance(delta, str) or len(result.answer) + len(delta) > 500_000:
                raise EvaluationError("invalid_stream")
            result.answer += delta
        elif event.event == "citations":
            if not isinstance(event.data.get("items"), list):
                raise EvaluationError("invalid_stream")
            result.citations = event.data["items"]
        elif event.event == "done":
            result.done = event.data
        elif event.event == "error":
            raise EvaluationError("stream_error")

    async def _stream_answer(self, conversation_id, question, request_id):
        result = StreamResult()
        start = time.monotonic()
        lines, events = LineDecoder(), SSEDecoder()
        try:
            async with asyncio.timeout(STREAM_TIMEOUT_SECONDS):
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    transport=self.transport,
                    cookies=self.http.cookies,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(30, connect=10),
                ) as client:
                    async with client.stream(
                        "POST",
                        f"/conversations/{resource_id(conversation_id)}/chat/stream",
                        json={"question": question, "request_id": request_id},
                    ) as response:
                        self._check(response)
                        if "text/event-stream" not in response.headers.get("content-type", ""):
                            raise EvaluationError("invalid_stream")
                        async for chunk in response.aiter_bytes():
                            if time.monotonic() - start > STREAM_TIMEOUT_SECONDS:
                                raise EvaluationError("network_error")
                            for line in lines.feed(chunk):
                                self._consume_event(result, events.feed(line))
                        for line in lines.finish():
                            self._consume_event(result, events.feed(line))
                        if not result.done or result.done.get("status") != "completed":
                            raise EvaluationError("incomplete_stream")
                if time.monotonic() - start > STREAM_TIMEOUT_SECONDS:
                    raise EvaluationError("network_error")
            result.elapsed_ms = round((time.monotonic() - start) * 1000)
            return result
        except (httpx.HTTPError, TimeoutError):
            raise EvaluationError("network_error") from None
        except (ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, EvaluationError):
                raise
            raise EvaluationError("invalid_stream") from None
