import asyncio
import json
import math
import time

import httpx
from langchain_core.embeddings import Embeddings

from app.core.config import Settings
from app.core.usage_context import current_usage

MODEL = "BAAI/bge-m3"
DIMENSIONS = 1024
URL = "https://api.siliconflow.cn/v1/embeddings"


class EmbeddingError(ValueError):
    pass


def validate_vectors(vectors: list, count: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != count:
        raise EmbeddingError("模型返回的向量数量不一致，请重试")
    checked = []
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != DIMENSIONS:
            raise EmbeddingError("模型返回的向量维度不是 1024，请检查模型配置")
        if any(type(value) not in {int, float} or not math.isfinite(value) for value in vector):
            raise EmbeddingError("模型返回了无效向量，请重试")
        norm = math.hypot(*vector)
        if norm == 0 or not math.isfinite(norm):
            raise EmbeddingError("模型返回了无效向量，请重试")
        checked.append([float(value) / norm for value in vector])
    return checked


class SiliconFlowEmbeddings(Embeddings):
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        key = settings.siliconflow_api_key
        if key is None or not key.get_secret_value().strip():
            raise EmbeddingError("请先在后端配置 SILICONFLOW_API_KEY")
        self._key = key
        self._settings = settings
        self._transport = transport

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.run(self.aembed_documents(texts))

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        deadline = time.monotonic() + self._settings.indexing_timeout_seconds
        try:
            async with asyncio.timeout(self._settings.indexing_timeout_seconds):
                return await self._generate(texts, deadline)
        except TimeoutError:
            raise EmbeddingError("索引请求超时，请稍后重试或拆分文档") from None

    async def _generate(self, texts: list[str], deadline: float) -> list[list[float]]:
        output = []
        async with httpx.AsyncClient(
            transport=self._transport, trust_env=False, follow_redirects=False
        ) as client:
            for offset in range(0, len(texts), self._settings.embedding_batch_size):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise EmbeddingError("索引请求超时，请稍后重试或拆分文档")
                batch = texts[offset : offset + self._settings.embedding_batch_size]
                recorder = current_usage()
                phase = (
                    "query_embedding"
                    if recorder and recorder.phase == "query_embedding"
                    else "index_embedding"
                )
                if recorder:
                    await recorder.before_provider(phase, MODEL)
                try:
                    async with client.stream(
                        "POST",
                        URL,
                        headers={"Authorization": f"Bearer {self._key.get_secret_value()}"},
                        json={"model": MODEL, "input": batch, "encoding_format": "float"},
                        timeout=httpx.Timeout(min(20, remaining), connect=min(5, remaining)),
                    ) as response:
                        if response.status_code in {401, 403}:
                            raise EmbeddingError("模型服务密钥无效或权限不足，请检查后端配置")
                        if response.status_code == 429:
                            raise EmbeddingError("模型服务请求频率受限，请稍后重试")
                        if response.status_code != 200:
                            raise EmbeddingError("模型服务暂不可用，请检查账户和模型权限后重试")
                        raw = bytearray()
                        async for part in response.aiter_bytes():
                            raw.extend(part)
                            if len(raw) > 2 * 1024 * 1024 or time.monotonic() > deadline:
                                raise EmbeddingError("模型响应过大或超时，请重试")
                        payload = json.loads(raw)
                    if recorder:
                        recorder.observe_tokens(
                            phase, payload.get("usage") if isinstance(payload, dict) else None
                        )
                    items = payload["data"]
                    if not isinstance(items, list) or len(items) != len(batch):
                        raise EmbeddingError("模型返回的向量数量不一致，请重试")
                    if any(type(item["index"]) is not int for item in items) or sorted(
                        item["index"] for item in items
                    ) != list(range(len(batch))):
                        raise EmbeddingError("模型返回的向量顺序无效，请重试")
                    items.sort(key=lambda item: item["index"])
                    output.extend(
                        validate_vectors([item["embedding"] for item in items], len(batch))
                    )
                    if time.monotonic() >= deadline:
                        raise EmbeddingError("索引请求超时，请稍后重试或拆分文档")
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as failure:
                    if isinstance(failure, EmbeddingError):
                        raise
                    raise EmbeddingError("模型请求失败或响应格式无效，请稍后重试") from None
        return output


def make_embeddings(settings: Settings) -> Embeddings:
    return SiliconFlowEmbeddings(settings)
