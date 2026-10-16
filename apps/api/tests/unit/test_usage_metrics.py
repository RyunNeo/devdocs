import asyncio

import httpx

from app.core.config import Settings
from app.core.usage_context import UsageRecorder, bind_usage
from app.rag.embeddings import SiliconFlowEmbeddings


def test_embedding_batches_preserve_partial_usage(monkeypatch):
    calls = []

    async def handle(request):
        calls.append(request)
        payload = {"data": [{"index": 0, "embedding": [1.0] + [0.0] * 1023}]}
        if len(calls) == 1:
            payload["usage"] = {"prompt_tokens": 7, "total_tokens": 7}
        return httpx.Response(200, json=payload)

    async def no_storage(*args):
        return True

    from app.services import usage_service

    monkeypatch.setattr(usage_service, "persist_attempt", lambda *args: True)
    recorder = UsageRecorder(None, None)
    client = SiliconFlowEmbeddings(
        Settings(siliconflow_api_key="fake-only", embedding_batch_size=1),
        transport=httpx.MockTransport(handle),
    )
    with bind_usage(recorder):
        assert len(asyncio.run(client.aembed_documents(["first", "second"]))) == 2
    result = recorder.snapshot()
    assert result.attempts["index_embedding"] == 2
    assert result.token_usage["index_embedding"]["known_tokens"] == 7
    assert result.token_usage["index_embedding"]["complete"] is False


def test_context_restored_and_invalid_metrics():
    from app.core.usage_context import current_usage
    from app.services.usage_service import normalize_token_usage

    recorder = UsageRecorder(None, None)
    with bind_usage(recorder):
        assert current_usage() is recorder
    assert current_usage() is None
    for value in [True, -1, 1.5, float("inf"), "123"]:
        assert normalize_token_usage({"total_tokens": value})["complete"] is False
    assert normalize_token_usage({"total_tokens": 1, "prompt_tokens": 4})["complete"] is False
