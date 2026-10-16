import json

import httpx
import pytest

from app.core.config import Settings
from app.rag.embeddings import EmbeddingError, SiliconFlowEmbeddings, validate_vectors


def test_batch_request_order_and_contract_without_real_api():
    calls = []

    def handler(request):
        assert str(request.url) == "https://api.siliconflow.cn/v1/embeddings"
        body = json.loads(request.content)
        assert body["model"] == "BAAI/bge-m3" and body["encoding_format"] == "float"
        calls.append(len(body["input"]))
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "index": index,
                        "embedding": [
                            1.0 if position == index else 0.0 for position in range(1024)
                        ],
                    }
                    for index in reversed(range(len(body["input"])))
                ]
            },
        )

    provider = SiliconFlowEmbeddings(
        Settings(siliconflow_api_key="test-only-value"), httpx.MockTransport(handler)
    )
    vectors = provider.embed_documents(["test"] * 17)
    assert calls == [16, 1]
    assert vectors[0][0] == 1 and vectors[1][1] == 1


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_provider_errors_never_echo_response_or_credentials(status):
    provider = SiliconFlowEmbeddings(
        Settings(siliconflow_api_key="test-only-value"),
        httpx.MockTransport(
            lambda request: httpx.Response(status, text="secret-provider-response")
        ),
    )
    with pytest.raises(EmbeddingError) as caught:
        provider.embed_query("sample")
    assert "secret-provider-response" not in str(caught.value)
    assert "test-only-value" not in str(caught.value)


@pytest.mark.parametrize(
    "vector",
    [[], [0.0] * 1024, [float("nan")] * 1024, [float("inf")] * 1024, [True] * 1024],
    ids=["dimension", "zero", "nan", "inf", "boolean"],
)
def test_invalid_vectors_are_rejected(vector):
    with pytest.raises(EmbeddingError):
        validate_vectors([vector], 1)


def test_malformed_response_indices_and_dimension():
    for payload in [
        {"data": [{"index": 1, "embedding": [1.0] * 1024}]},
        {"data": [{"index": 0, "embedding": [1.0]}]},
        {"data": []},
    ]:
        provider = SiliconFlowEmbeddings(
            Settings(siliconflow_api_key="test-only-value"),
            httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
        )
        with pytest.raises(EmbeddingError):
            provider.embed_query("sample")


def test_end_of_stream_cannot_publish_after_deadline():
    import asyncio
    import time

    payload = json.dumps({"data": [{"index": 0, "embedding": [1.0] + [0.0] * 1023}]}).encode()

    class SlowEOF(httpx.SyncByteStream, httpx.AsyncByteStream):
        def __iter__(self):
            yield payload
            time.sleep(0.4)

        async def __aiter__(self):
            yield payload
            await asyncio.sleep(0.4)

    settings = Settings(siliconflow_api_key="test-only-value").model_copy(
        update={"indexing_timeout_seconds": 0.25}
    )
    provider = SiliconFlowEmbeddings(
        settings, httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowEOF()))
    )
    with pytest.raises(EmbeddingError, match="超时"):
        provider.embed_query("test")
