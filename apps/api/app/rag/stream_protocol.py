import codecs
import json


class SSEDecoder:
    def __init__(self, max_frame_bytes=65536):
        self.decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self.buffer = ""
        self.lines = []
        self.size = 0
        self.limit = max_frame_bytes

    def feed(self, chunk: bytes):
        self.buffer += self.decoder.decode(chunk)
        frames = []
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.removesuffix("\r")
            self.size += len(line.encode()) + 1
            if self.size > self.limit:
                raise ValueError("SSE frame limit")
            if line:
                self.lines.append(line)
            else:
                event = "message"
                data = []
                for item in self.lines:
                    if item.startswith(":"):
                        continue
                    field, _, value = item.partition(":")
                    value = value.removeprefix(" ")
                    if field == "event":
                        event = value
                    elif field == "data":
                        data.append(value)
                if data:
                    frames.append((event, "\n".join(data)))
                self.lines = []
                self.size = 0
        if self.size + len(self.buffer.encode()) > self.limit:
            raise ValueError("SSE frame limit")
        return frames

    def finish(self):
        self.decoder.decode(b"", final=True)
        if self.buffer.strip() or self.lines:
            raise ValueError("Incomplete SSE frame")


def encode_sse(event: str, payload: dict) -> bytes:
    prefix = f"event: {event}\n" if event else ""
    return (
        prefix + "data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n\n"
    ).encode()
