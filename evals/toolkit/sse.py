import codecs
import json
import time
from dataclasses import dataclass
from typing import Iterable, Iterator

MAX_EVENT = 1024 * 1024


@dataclass
class SSEEvent:
    event: str
    data: dict


class LineDecoder:
    def __init__(self):
        self.decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self.buffer = ""

    def feed(self, chunk: bytes) -> Iterator[str]:
        self.buffer += self.decoder.decode(chunk)
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if len(line.encode("utf-8")) > MAX_EVENT:
                raise ValueError("event_too_large")
            yield line.removesuffix("\r")
        if len(self.buffer.encode("utf-8")) > MAX_EVENT:
            raise ValueError("event_too_large")

    def finish(self) -> list[str]:
        self.buffer += self.decoder.decode(b"", final=True)
        return [self.buffer.removesuffix("\r")] if self.buffer else []


def bounded_lines(chunks: Iterable[bytes], deadline: float) -> Iterator[str]:
    decoder = LineDecoder()
    for chunk in chunks:
        if time.monotonic() > deadline:
            raise ValueError("stream_timeout")
        yield from decoder.feed(chunk)
    if time.monotonic() > deadline:
        raise ValueError("stream_timeout")
    yield from decoder.finish()


class SSEDecoder:
    def __init__(self):
        self.event, self.data, self.size = "message", [], 0

    def feed(self, line: str) -> SSEEvent | None:
        self.size += len(line.encode("utf-8"))
        if self.size > MAX_EVENT:
            raise ValueError("event_too_large")
        if not line:
            result = None
            if self.data and self.event in {
                "meta",
                "token",
                "citations",
                "done",
                "error",
                "status",
            }:
                payload = json.loads("\n".join(self.data))
                if not isinstance(payload, dict):
                    raise ValueError("invalid_event")
                result = SSEEvent(self.event, payload)
            self.event, self.data, self.size = "message", [], 0
            return result
        elif not line.startswith(":"):
            key, sep, value = line.partition(":")
            value = value.removeprefix(" ") if sep else ""
            if key == "event":
                self.event = value
            elif key == "data":
                self.data.append(value)
        return None


def iter_sse(lines: Iterable[str]) -> Iterator[SSEEvent]:
    decoder = SSEDecoder()
    for line in lines:
        event = decoder.feed(line)
        if event:
            yield event
