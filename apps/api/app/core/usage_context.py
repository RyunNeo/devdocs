from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic

import anyio


@dataclass
class UsageMetrics:
    durations_ms: dict = field(default_factory=dict)
    models: dict = field(default_factory=dict)
    attempts: dict = field(default_factory=dict)
    token_usage: dict = field(default_factory=dict)


_current = ContextVar("usage_recorder", default=None)


def current_usage():
    return _current.get()


@contextmanager
def bind_usage(recorder):
    token = _current.set(recorder)
    try:
        yield recorder
    finally:
        _current.reset(token)


class UsageRecorder:
    def __init__(self, factory, event_id):
        self.factory, self.event_id = factory, event_id
        self.metrics = UsageMetrics()
        self.phase = None

    @contextmanager
    def stage(self, name):
        started = monotonic()
        previous, self.phase = self.phase, name
        try:
            yield
        except BaseException:
            self.metrics.durations_ms[name] = None
            raise
        else:
            self.metrics.durations_ms[name] = round((monotonic() - started) * 1000)
        finally:
            self.phase = previous

    async def before_provider(self, phase, model):
        from app.services.usage_service import persist_attempt

        self.metrics.models[phase] = model
        self.metrics.attempts[phase] = self.metrics.attempts.get(phase, 0) + 1
        if not await anyio.to_thread.run_sync(
            persist_attempt, self.factory, self.event_id, self.metrics
        ):
            raise RuntimeError("Usage operation is no longer active")

    def observe_tokens(self, phase, raw):
        from app.services.usage_service import normalize_token_usage

        item = normalize_token_usage(raw)
        if phase == "chat":
            self.metrics.token_usage[phase] = item
        else:
            previous = self.metrics.token_usage.get(
                phase, {"known_tokens": 0, "complete": True, "batches": 0}
            )
            self.metrics.token_usage[phase] = {
                "known_tokens": previous["known_tokens"] + item["known_tokens"],
                "complete": previous["complete"] and item["complete"],
                "batches": previous["batches"] + 1,
            }

    def snapshot(self):
        import copy

        result = copy.deepcopy(self.metrics)
        for phase, count in result.attempts.items():
            usage = result.token_usage.setdefault(phase, {"known_tokens": 0, "complete": False})
            if phase != "chat" and usage.get("batches", 0) != count:
                usage["complete"] = False
        return result
