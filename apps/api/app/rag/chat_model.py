import asyncio
import json
import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.core.usage_context import current_usage
from app.rag.stream_protocol import SSEDecoder

URL = "https://api.siliconflow.cn/v1/chat/completions"


class ChatModelError(ValueError):
    def __init__(self, code="provider_failed", message="回答服务暂不可用，请稍后重试"):
        super().__init__(message)
        self.code = code


@dataclass
class ProviderEvent:
    kind: str
    data: dict


class SiliconFlowChatModel:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.transport = transport

    async def astream(self, messages: list[dict[str, str]], deadline: float):
        key = self.settings.siliconflow_api_key
        if key is None or not key.get_secret_value().strip():
            raise ChatModelError("missing_config", "请先配置 SILICONFLOW_API_KEY")
        try:
            async with asyncio.timeout(max(0, deadline - time.monotonic())):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(20, connect=5),
                ) as client:
                    recorder = current_usage()
                    if recorder:
                        await recorder.before_provider("chat", self.settings.chat_model)
                    async with client.stream(
                        "POST",
                        URL,
                        headers={"Authorization": f"Bearer {key.get_secret_value()}"},
                        json={
                            "model": self.settings.chat_model,
                            "messages": messages,
                            "stream": True,
                            "max_tokens": self.settings.chat_max_tokens,
                            "enable_thinking": False,
                        },
                    ) as response:
                        if response.status_code != 200:
                            raise ChatModelError(
                                "provider_rejected", "模型服务拒绝请求，请检查模型权限、密钥或额度"
                            )
                        if "text/event-stream" not in response.headers.get("content-type", ""):
                            raise ChatModelError("invalid_stream", "模型未返回流式回答")
                        decoder = SSEDecoder()
                        total = 0
                        stopped = False
                        done = False
                        content = False
                        async for chunk in response.aiter_bytes():
                            total += len(chunk)
                            if total > 1024 * 1024 or time.monotonic() >= deadline:
                                raise ChatModelError("stream_limit", "回答超过时间或大小限制")
                            for _, data in decoder.feed(chunk):
                                if done:
                                    raise ChatModelError("invalid_stream", "回答流格式错误")
                                if data == "[DONE]":
                                    done = True
                                    continue
                                payload = json.loads(data)
                                if not isinstance(payload, dict) or "error" in payload:
                                    raise ChatModelError()
                                usage = payload.get("usage")
                                if isinstance(usage, dict):
                                    if recorder:
                                        recorder.observe_tokens("chat", usage)
                                    safe = {
                                        k: v
                                        for k, v in usage.items()
                                        if k
                                        in {"prompt_tokens", "completion_tokens", "total_tokens"}
                                        and type(v) is int
                                        and v >= 0
                                    }
                                    if safe:
                                        yield ProviderEvent("usage", safe)
                                choices = payload.get("choices", [])
                                if not isinstance(choices, list) or len(choices) > 1:
                                    raise ChatModelError()
                                for choice in choices:
                                    delta = choice.get("delta", {})
                                    text = delta.get("content")
                                    if text is not None and not isinstance(text, str):
                                        raise ChatModelError()
                                    if text:
                                        if stopped:
                                            raise ChatModelError()
                                        content = True
                                        yield ProviderEvent("token", {"delta": text})
                                    finish = choice.get("finish_reason")
                                    if finish is not None:
                                        if finish != "stop" or stopped:
                                            raise ChatModelError(
                                                "truncated", "回答未完整生成，请重新提问"
                                            )
                                        stopped = True
                        decoder.finish()
                        if not (done and stopped and content):
                            raise ChatModelError("interrupted", "回答流已中断，未收到完整答案")
                        yield ProviderEvent("finish", {"finish_reason": "stop"})
        except ChatModelError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise ChatModelError("timeout", "回答超时，请稍后重试") from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            raise ChatModelError("invalid_stream", "回答服务连接或流格式异常") from None


def make_chat_model(settings):
    return SiliconFlowChatModel(settings)
