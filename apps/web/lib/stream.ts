import type { ChatEvent } from "../../../packages/shared/types/chat";
import { ApiError } from "./api";

export async function readChatStream(response: Response, onEvent: (event: ChatEvent) => void, signal: AbortSignal): Promise<void> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(typeof payload?.detail === "string" ? payload.detail : "问答服务暂不可用", response.status);
  }
  if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream")) throw new Error("未收到回答流");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffer = "", lines: string[] = [], size = 0, total = 0, terminal = false, meta = false;
  const abort = () => { void reader.cancel(); };
  signal.addEventListener("abort", abort, { once: true });
  try {
    if (signal.aborted) throw new Error("请求已停止");
    while (!terminal) {
      const { value, done } = await reader.read();
      if (signal.aborted) throw new Error("请求已停止");
      if (done) { decoder.decode(); break; }
      total += value.byteLength;
      if (total > 2 * 1024 * 1024) throw new Error("回答超过大小限制");
      buffer += decoder.decode(value, { stream: true });
      while (buffer.includes("\n") && !terminal) {
        const position = buffer.indexOf("\n");
        const line = buffer.slice(0, position).replace(/\r$/, "");
        buffer = buffer.slice(position + 1);
        size += new TextEncoder().encode(line).length + 1;
        if (size > 65536) throw new Error("回答流格式异常");
        if (line) { lines.push(line); continue; }
        let event = "message";
        const data: string[] = [];
        for (const item of lines) {
          const colon = item.indexOf(":");
          const field = colon < 0 ? item : item.slice(0, colon);
          const value = colon < 0 ? "" : item.slice(colon + 1).replace(/^ /, "");
          if (field === "event") event = value;
          else if (field === "data") data.push(value);
        }
        lines = []; size = 0;
        if (!data.length) continue;
        const payload = JSON.parse(data.join("\n"));
        if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("回答流格式异常");
        if (event === "meta") {
          if (meta || typeof payload.run_id !== "string" || typeof payload.assistant_message_id !== "string" || typeof payload.conversation_id !== "string") throw new Error("回答流格式异常");
          meta = true;
        } else if (!meta) throw new Error("回答流缺少请求信息");
        if (event === "token" && typeof payload.delta !== "string") throw new Error("回答流格式异常");
        if (event === "status" && !["retrieving", "generating", "validating"].includes(payload.phase)) throw new Error("回答阶段异常");
        if (event === "citations" && (!Array.isArray(payload.items) || payload.items.some((item: unknown) => {
          if (!item || typeof item !== "object") return true;
          const c = item as Record<string, unknown>;
          return !Number.isInteger(c.number) || typeof c.content !== "string" || typeof c.filename !== "string" || !c.metadata || typeof c.metadata !== "object";
        }))) throw new Error("引用格式异常");
        if (event === "done" && (payload.status !== "completed" || (payload.content !== undefined && typeof payload.content !== "string"))) throw new Error("回答终态异常");
        if (event === "error" && (typeof payload.message !== "string" || typeof payload.code !== "string")) throw new Error("回答流格式异常");
        if (!["meta", "status", "token", "citations", "done", "error"].includes(event)) throw new Error("未知回答事件");
        onEvent({ event, data: payload } as ChatEvent);
        terminal = event === "done" || event === "error";
      }
      if (new TextEncoder().encode(buffer).length + size > 65536) throw new Error("回答流格式异常");
    }
    if (!terminal) throw new Error("回答连接已中断，结果尚未确认，请刷新会话");
  } finally {
    signal.removeEventListener("abort", abort);
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
