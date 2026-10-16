import { test, expect } from "@playwright/test";
import { readChatStream } from "../../lib/stream";

function response(text: string) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
    controller.close();
  } }), { headers: { "content-type": "text/event-stream" } });
}

const meta = 'event: meta\r\ndata: {"conversation_id":"c","run_id":"r","assistant_message_id":"m"}\r\n\r\n';

test("stream parser preserves split Chinese and multiline data", async () => {
  let answer = '';
  await readChatStream(response(meta + 'event: token\r\ndata: {"delta":\r\ndata: "中文"}\r\n\r\n'
    + 'event: done\ndata: {"status":"completed","content":"中文","message_id":"m"}\n\n'), (event) => {
    if (event.event === 'token') answer += event.data.delta;
  }, new AbortController().signal);
  expect(answer).toBe('中文');
});

test("stream parser rejects missing terminal and malformed frame", async () => {
  await expect(readChatStream(response(meta), () => {}, new AbortController().signal)).rejects.toThrow('中断');
  await expect(readChatStream(response(meta + 'event: token\ndata: {bad}\n\n'), () => {}, new AbortController().signal)).rejects.toThrow();
});

test("stream parser validates processing phases", async () => {
  const phases:string[]=[];
  const status=['retrieving','generating','validating'].map(phase=>`event: status\ndata: ${JSON.stringify({phase})}\n\n`).join('');
  await readChatStream(response(meta+status+'event: done\ndata: {"status":"completed","message_id":"m"}\n\n'),event=>{
    if(event.event==='status') phases.push(event.data.phase);
  },new AbortController().signal);
  expect(phases).toEqual(['retrieving','generating','validating']);
  await expect(readChatStream(response(meta+'event: status\ndata: {"phase":"unknown"}\n\n'),()=>{},new AbortController().signal)).rejects.toThrow('阶段');
});
