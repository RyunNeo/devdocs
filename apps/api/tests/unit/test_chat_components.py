import asyncio
import json
import time
from uuid import uuid4

import httpx
import pytest


def test_citation_validation_and_insufficient():
    from app.rag.citations import CitationError, validate_answer
    from app.rag.retriever import RetrievedSource

    source = RetrievedSource(1, uuid4(), uuid4(), 0, "notes.md", "正文", {}, 0.8, "fp")
    assert validate_answer("答案 [1]", [source]).citations[0]["content"] == "正文"
    for text in ["答案 [99]", "没有引用的答案"]:
        with pytest.raises(CitationError):
            validate_answer(text, [source])
    assert validate_answer("[[INSUFFICIENT_EVIDENCE]]", []).insufficient


def test_mixed_insufficient_answer_discards_speculation_and_citations():
    from app.rag.citations import INSUFFICIENT, validate_answer
    from app.rag.retriever import RetrievedSource

    source = RetrievedSource(1, uuid4(), uuid4(), 0, "README.md", "工程目录", {}, 0.8, "fp")
    result = validate_answer("从目录推测定位如下 [1]。\n[[INSUFFICIENT_EVIDENCE]]", [source])
    assert result.insufficient is True
    assert result.content == INSUFFICIENT
    assert result.citations == []


def test_context_budget_and_untrusted_boundary():
    from app.rag.prompts import build_prompt_messages, build_retrieval_query
    from app.rag.retriever import RetrievedSource, budget_sources

    sources = [
        RetrievedSource(i, uuid4(), uuid4(), 0, "文档.md", "中" * 660, {}, 0.8, "fp")
        for i in range(1, 9)
    ]
    bounded = budget_sources(sources, 12000)
    assert sum(len(x.content.encode()) for x in bounded) <= 12000
    prompt = build_prompt_messages("问题", [], bounded)
    assert "不可信" in prompt[0]["content"]
    assert build_retrieval_query("问题", []) == "问题"


def test_sse_arbitrary_utf8_chunks():
    from app.rag.stream_protocol import SSEDecoder

    raw = 'event: token\r\ndata: {"delta":\r\ndata: "中文"}\r\n\r\n'.encode()
    decoder = SSEDecoder()
    frames = []
    for byte in raw:
        frames.extend(decoder.feed(bytes([byte])))
    assert frames == [("token", '{"delta":\n"中文"}')]


@pytest.mark.parametrize("finish", ["stop", "length", None])
def test_model_requires_successful_finish(finish):
    from app.core.config import Settings
    from app.rag.chat_model import ChatModelError, SiliconFlowChatModel
    from app.rag.stream_protocol import encode_sse

    def handle(request):
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-ai/DeepSeek-V4-Flash"
        assert payload["stream"] is True
        data = encode_sse(
            "",
            {
                "choices": [
                    {
                        "delta": {"content": "答案 [1]", "reasoning_content": "hidden"},
                        "finish_reason": finish,
                    }
                ]
            },
        )
        return httpx.Response(
            200, content=data + b"data: [DONE]\n\n", headers={"content-type": "text/event-stream"}
        )

    async def run():
        model = SiliconFlowChatModel(
            Settings(siliconflow_api_key="test-secret"), httpx.MockTransport(handle)
        )
        return [event async for event in model.astream([], time.monotonic() + 5)]

    if finish == "stop":
        events = asyncio.run(run())
        assert events[0].data == {"delta": "答案 [1]"}
    else:
        with pytest.raises(ChatModelError):
            asyncio.run(run())


@pytest.mark.parametrize(
    "body",
    [
        b"data: {bad}\n\n",
        b'data: {"error":{"message":"private-secret"}}\n\n',
        b"data: " + b"x" * 65537 + b"\n\n",
        b'data: {"choices":[{"delta":{"reasoning_content":"hidden"},'
        b'"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
    ],
    ids=["invalid-json", "provider-error", "frame-too-large", "reasoning-only"],
)
def test_provider_bad_stream_does_not_leak(body):
    from app.core.config import Settings
    from app.rag.chat_model import ChatModelError, SiliconFlowChatModel

    async def run():
        model = SiliconFlowChatModel(
            Settings(siliconflow_api_key="private-secret"),
            httpx.MockTransport(
                lambda request: httpx.Response(
                    200, content=body, headers={"content-type": "text/event-stream"}
                )
            ),
        )
        return [event async for event in model.astream([], time.monotonic() + 5)]

    with pytest.raises(ChatModelError) as failure:
        asyncio.run(run())
    assert "private-secret" not in str(failure.value)


def test_expired_absolute_deadline():
    from app.core.config import Settings
    from app.rag.chat_model import ChatModelError, SiliconFlowChatModel

    async def run():
        async def handle(request):
            await asyncio.sleep(1)
            return httpx.Response(200)

        model = SiliconFlowChatModel(
            Settings(siliconflow_api_key="fake"), httpx.MockTransport(handle)
        )
        return [event async for event in model.astream([], time.monotonic() + 0.01)]

    with pytest.raises(ChatModelError) as failure:
        asyncio.run(run())
    assert failure.value.code == "timeout"


def test_long_heading_is_bounded_in_serialized_sources():
    from app.rag.prompts import build_prompt_messages
    from app.rag.retriever import RetrievedSource, budget_sources

    source = RetrievedSource(
        1, uuid4(), uuid4(), 0, "notes.md", "short body", {"Header 1": "中" * 70000}, 0.9, "fp"
    )
    sources = budget_sources([source])
    assert sources
    serialized = build_prompt_messages("问题", [], sources)[-1]["content"]
    assert len(serialized.encode()) < 12500


def test_followup_uses_latest_completed_question_even_if_answer_too_long():
    from types import SimpleNamespace

    from app.rag.prompts import build_retrieval_query

    history = [
        SimpleNamespace(role="user", status="completed", run_id="a", content="React state"),
        SimpleNamespace(role="assistant", status="completed", run_id="a", content="short"),
        SimpleNamespace(role="user", status="completed", run_id="b", content="Python generators"),
        SimpleNamespace(role="assistant", status="completed", run_id="b", content="x" * 7000),
    ]
    assert build_retrieval_query("their memory use?", history).startswith("Python generators")
