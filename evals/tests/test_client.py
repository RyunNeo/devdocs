import httpx
import pytest


def client_for(handler):
    from evals.toolkit.client import EvaluationClient

    return EvaluationClient("http://127.0.0.1:8000", transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://example.com",
        "http://user:pass@localhost",
        "http://localhost?key=secret",
        "http://localhost/#bad",
        "ftp://localhost",
    ],
)
def test_reject_unsafe_url(url):
    from evals.toolkit.client import EvaluationClient

    with pytest.raises(ValueError):
        EvaluationClient(url)


def test_status_no_retry_or_redirect():
    from evals.toolkit.client import EvaluationError

    for status in (401, 429, 302):
        calls = []

        def handler(req):
            calls.append(req)
            return httpx.Response(
                status, headers={"location": "https://example.com"}, text="secret-password"
            )

        with client_for(handler) as client:
            with pytest.raises(EvaluationError) as error:
                client.login("tester@example.com", "secret-password")
            assert "secret-password" not in str(error.value)
        assert len(calls) == 1


def test_index_business_failure():
    from evals.toolkit.client import EvaluationError

    with client_for(lambda req: httpx.Response(200, json={"index_status": "failed"})) as client:
        with pytest.raises(EvaluationError, match="index_failed"):
            client.index("doc")


def test_duplicate_kb_has_specific_safe_hint():
    from evals.toolkit.client import EvaluationError

    with client_for(lambda req: httpx.Response(409, text="secret response")) as client:
        with pytest.raises(EvaluationError, match="knowledge_base_name_conflict") as exc:
            client.create_kb("existing")
    assert "运行编号" in str(exc.value)
    assert "secret response" not in str(exc.value)


class Bytes(httpx.SyncByteStream, httpx.AsyncByteStream):
    def __init__(self, body):
        self.body = body

    def __iter__(self):
        for byte in self.body:
            yield bytes([byte])

    async def __aiter__(self):
        for byte in self.body:
            yield bytes([byte])


def test_sse_utf8_fragmentation_and_heartbeat():
    body = ': heartbeat\r\n\r\nevent: meta\r\ndata: {"run_id":"r"}\r\n\r\n'
    body += 'event: token\ndata: {"delta":"中文[1]"}\n\n'
    body += 'event: citations\ndata: {"items": []}\n\n'
    body += 'event: done\ndata: {"status":\ndata: "completed","message_id":"m"}\n\n'
    with client_for(
        lambda req: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=Bytes(body.encode())
        )
    ) as client:
        result = client.stream_answer("c", "q", "r")
    assert result.answer == "中文[1]"
    assert result.done["message_id"] == "m"


@pytest.mark.parametrize(
    "body",
    [
        'event: token\ndata: {"delta":"x"}\n\n',
        "event: done\ndata: not-json\n\n",
        'event: error\ndata: {"message":"secret"}\n\n',
        "event: done\ndata: " + "x" * (1024 * 1024 + 1) + "\n\n",
    ],
    ids=["missing-done", "bad-json", "error", "oversized"],
)
def test_invalid_stream(body):
    from evals.toolkit.client import EvaluationError

    with client_for(
        lambda req: httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)
    ) as client:
        with pytest.raises(EvaluationError):
            client.stream_answer("c", "q", "r")


def test_read_timeout_redacted():
    from evals.toolkit.client import EvaluationError

    def handler(req):
        raise httpx.ReadTimeout("Cookie=secret")

    with client_for(handler) as client:
        with pytest.raises(EvaluationError) as exc:
            client.summary()
        assert "secret" not in str(exc.value)


def test_paginated_documents():
    def handler(req):
        offset = int(req.url.params.get("offset", 0))
        return httpx.Response(200, json={"total": 2, "items": [{"id": str(offset)}]})

    with client_for(handler) as client:
        assert len(client.list_documents("kb")) == 2


def test_remote_and_heartbeat_deadline(monkeypatch):
    from evals.toolkit.client import EvaluationClient
    from evals.toolkit.sse import bounded_lines

    with EvaluationClient("https://example.com", allow_remote=True):
        pass
    with pytest.raises(ValueError):
        EvaluationClient("http://example.com", allow_remote=True)
    monkeypatch.setattr("evals.toolkit.sse.time.monotonic", lambda: 181)
    with pytest.raises(ValueError, match="stream_timeout"):
        list(bounded_lines([b": heartbeat\n\n"], 180))


def test_total_deadline_includes_waiting_for_eof(monkeypatch):
    import asyncio

    from evals.toolkit import client as module

    class SlowEOF(httpx.SyncByteStream, httpx.AsyncByteStream):
        def __iter__(self):
            import time

            yield b'event: done\ndata: {"status":"completed"}\n\n'
            time.sleep(0.1)

        async def __aiter__(self):
            yield b'event: done\ndata: {"status":"completed"}\n\n'
            await asyncio.sleep(0.1)

    monkeypatch.setattr(module, "STREAM_TIMEOUT_SECONDS", 0.02, raising=False)
    with client_for(
        lambda req: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=SlowEOF()
        )
    ) as client:
        with pytest.raises(module.EvaluationError):
            client.stream_answer("c", "q", "r")
