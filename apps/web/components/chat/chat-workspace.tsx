"use client";
import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import { readChatStream } from "@/lib/stream";
import { ChatComposer } from "./chat-composer";
import { MessageList } from "./message-list";
import { CitationDialog } from "./citation-dialog";
import { useKnowledgeBaseWorkspace } from "@/components/knowledge-bases/knowledge-base-workspace";
import type { ChatMessage, Citation, ConversationDetail, ConversationList } from "../../../../packages/shared/types/conversation";
import type { ChatEvent } from "../../../../packages/shared/types/chat";

export function ChatWorkspace({ knowledgeBaseId, initialConversation, startNew = false }: { knowledgeBaseId: string; initialConversation: string | null; startNew?: boolean }) {
  const router = useRouter();
  const { setNavigationBusy } = useKnowledgeBaseWorkspace();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [older, setOlder] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [revision, setRevision] = useState(0);
  const [phase, setPhase] = useState<"retrieving" | "generating" | "validating">("retrieving");
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [presentationRunId, setPresentationRunId] = useState<string | null>(null);
  const conversation = useRef(initialConversation);
  const explicitNew = useRef(startNew);
  const olderController = useRef<AbortController | null>(null);
  const olderInFlight = useRef(false);
  const scrollAnchor = useRef<{ id: string; top: number } | null>(null);
  const active = useRef<{ id: string; controller: AbortController; stopped: boolean; completed: boolean } | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const citationTrigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    setNavigationBusy(busy);
    return () => setNavigationBusy(false);
  }, [busy, setNavigationBusy]);

  function handleFailure(failure: unknown) {
    if (failure instanceof ApiError && failure.status === 401) { router.replace("/login"); router.refresh(); return; }
    if (failure instanceof ApiError && failure.status === 404) setBlocked(true);
    setError(failure instanceof Error ? failure.message : "问答暂不可用");
  }

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]);
    setLoading(true); setError(""); setBlocked(false); setPresentationRunId(null);
    (async () => {
      let target = conversation.current;
      if (!target && !explicitNew.current) {
        const recent = await apiRequest<ConversationList>(`/knowledge-bases/${knowledgeBaseId}/conversations?limit=1&offset=0`, undefined, signal);
        if (controller.signal.aborted) return;
        target = recent.items[0]?.id ?? null;
      }
      if (target) {
        const detail = await apiRequest<ConversationDetail>(`/conversations/${target}`, undefined, signal);
        if (controller.signal.aborted) return;
        if (detail.knowledge_base_id !== knowledgeBaseId) throw new ApiError("会话不属于这个知识库", 404);
        conversation.current = target;
        setMessages(detail.messages); setOlder(detail.has_older);
        window.history.replaceState(null, "", `${window.location.pathname}?conversation=${encodeURIComponent(target)}`);
      } else { setMessages([]); setOlder(false); }
    })().catch((failure) => { if (!controller.signal.aborted) handleFailure(failure); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { mounted.current = false; controller.abort(); olderController.current?.abort(); active.current?.controller.abort(); };
  // The identity is fixed for this page; refresh uses revision without recreating a conversation.
  }, [knowledgeBaseId, revision]);

  useLayoutEffect(() => {
    const anchor = scrollAnchor.current;
    if (!anchor) return;
    const element = document.getElementById(`chat-message-${anchor.id}`);
    if (element) window.scrollBy(0, element.getBoundingClientRect().top - anchor.top);
    scrollAnchor.current = null;
  }, [messages]);

  async function loadOlder() {
    const id = conversation.current;
    const boundary = messages[0]?.sequence;
    if (!id || !boundary || inFlight.current || olderInFlight.current) return;
    olderInFlight.current = true; setLoadingOlder(true); setError("");
    const controller = new AbortController(); olderController.current = controller;
    try {
      const detail = await apiRequest<ConversationDetail>(`/conversations/${id}?before_sequence=${boundary}&limit=40`, undefined,
        AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]));
      if (controller.signal.aborted || conversation.current !== id || !mounted.current) return;
      const anchor = messages[0];
      const element = anchor && document.getElementById(`chat-message-${anchor.id}`);
      if (element) scrollAnchor.current = { id: anchor.id, top: element.getBoundingClientRect().top };
      setMessages((previous) => {
        const existing = new Set(previous.map((m) => m.id));
        return [...detail.messages.filter((m) => !existing.has(m.id)), ...previous];
      });
      setOlder(detail.has_older);
    } catch (failure) { if (!controller.signal.aborted && mounted.current) handleFailure(failure); }
    finally { if (olderController.current === controller) { olderInFlight.current = false; if (mounted.current) setLoadingOlder(false); } }
  }

  function newConversation() {
    if (inFlight.current) return;
    olderController.current?.abort(); olderController.current = null; olderInFlight.current = false;
    explicitNew.current = true; conversation.current = null; scrollAnchor.current = null;
    setMessages([]); setQuestion(""); setOlder(false); setLoadingOlder(false); setBlocked(false); setError(""); setPresentationRunId(null);
    window.history.replaceState(null, "", `${window.location.pathname}?new=1`);
  }

  function updateAnswer(runId: string, update: Partial<ChatMessage>) {
    setMessages((previous) => previous.map((m) => m.run_id === runId && m.role === "assistant" ? { ...m, ...update } : m));
  }

  async function send() {
    if (inFlight.current || olderInFlight.current || loading || blocked || !question.trim()) return;
    inFlight.current = true; setBusy(true); setError(""); setPhase("retrieving"); setPresentationRunId(null);
    const text = question.trim();
    const run = { id: crypto.randomUUID(), controller: new AbortController(), stopped: false, completed: false };
    active.current = run;
    const timeout = setTimeout(() => run.controller.abort(), 110000);
    let accepted = false;
    try {
      if (conversation.current) {
        const latest = await apiRequest<ConversationDetail>(`/conversations/${conversation.current}`, undefined,
          AbortSignal.any([run.controller.signal, AbortSignal.timeout(10000)]));
        if (latest.knowledge_base_id !== knowledgeBaseId) throw new ApiError("会话不属于这个知识库", 404);
        const firstLoaded = messages[0]?.sequence;
        setMessages((previous) => {
          const bySequence = new Map(previous.map((message) => [message.sequence, message]));
          for (const message of latest.messages) bySequence.set(message.sequence, message);
          return [...bySequence.values()].sort((a,b) => a.sequence-b.sequence);
        });
        setOlder((previous) => firstLoaded && firstLoaded < (latest.messages[0]?.sequence ?? 0) ? previous : latest.has_older);
        if (latest.messages.some((message) => message.role === "assistant" && message.status === "streaming")) {
          throw new ApiError("当前会话正在其他页面回答，请等待完成后刷新",409);
        }
      }
      if (!conversation.current) {
        const created = await apiRequest<{ id: string }>(`/knowledge-bases/${knowledgeBaseId}/conversations`, {},
          AbortSignal.any([run.controller.signal, AbortSignal.timeout(10000)]));
        conversation.current = created.id;
        explicitNew.current = false;
        window.history.replaceState(null, "", `${window.location.pathname}?conversation=${created.id}`);
      }
      const response = await fetch(`/api/conversations/${conversation.current}/chat/stream`, { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: text, request_id: run.id }), signal: run.controller.signal });
      await readChatStream(response, (event: ChatEvent) => {
        if (!mounted.current) return;
        if (event.event === "meta") {
          accepted = true; setQuestion("");
          setMessages((previous) => {
            const sequence = event.data.user_sequence ?? Math.max(0,...previous.map((m) => m.sequence)) + 1;
            return [...previous,
              { id: `${run.id}-user`, role: "user", content: text, status: "completed", run_id: run.id, sequence, citations: [], error_code: null },
              { id: event.data.assistant_message_id, role: "assistant", content: "", status: "streaming", run_id: run.id, sequence: sequence+1, citations: [], error_code: null }];
          });
        } else if (event.event === "status") setPhase(event.data.phase);
        else if (event.event === "token") {
          setMessages((previous) => previous.map((m) => m.run_id === run.id && m.role === "assistant" ? { ...m, content: m.content + event.data.delta } : m));
        } else if (event.event === "citations") updateAnswer(run.id, { citations: event.data.items });
        else if (event.event === "done") { run.completed = true; setPresentationRunId(run.id); updateAnswer(run.id, { status: "completed", ...(event.data.content !== undefined ? { content: event.data.content } : {}), usage: event.data.usage }); }
        else if (event.event === "error") { updateAnswer(run.id, { status: event.data.code === "cancelled" ? "cancelled" : "failed", error_code: event.data.code }); setError(event.data.message); }
      }, run.controller.signal);
    } catch (failure) {
      if (!mounted.current) return;
      if (!run.completed && accepted) updateAnswer(run.id, { status: run.stopped ? "cancelled" : "failed", error_code: run.stopped ? "cancelled" : "interrupted" });
      if (!run.stopped) handleFailure(run.controller.signal.aborted ? new Error("等待已结束，请刷新会话确认结果") : failure);
    } finally {
      clearTimeout(timeout); inFlight.current = false;
      if (active.current === run) active.current = null;
      if (mounted.current) setBusy(false);
    }
  }

  function stop() {
    const run = active.current;
    if (!run || run.completed) return;
    run.stopped = true; run.controller.abort();
    if (conversation.current) void apiRequest(`/conversations/${conversation.current}/chat/cancel`, { run_id: run.id }, AbortSignal.timeout(10000))
      .catch(() => { if (mounted.current) setError("停止请求未确认，请刷新会话查看结果"); });
  }

  return <div className="chat-workspace">
    <div className="knowledge-content-toolbar"><div className="pagination-buttons">
      <button className="icon-button" aria-label="刷新会话" title="刷新会话" disabled={busy || loading || loadingOlder} onClick={() => { setLoading(true); setRevision((v) => v+1); }}><RefreshCw size={18} /></button>
      <button className="icon-button" aria-label="新会话" title="新会话" disabled={busy || loading} onClick={newConversation}><Plus size={20} /></button>
    </div></div>
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    {loading ? <p role="status">正在加载会话…</p> : <>
      {older ? <button className="text-button" disabled={busy || loadingOlder} onClick={loadOlder}>{loadingOlder ? "正在加载更早消息" : "加载更早消息"}</button> : null}
      {!messages.length ? <div className="chat-empty"><p>暂无消息</p></div> : <MessageList messages={messages} phase={phase} activeRunId={busy ? active.current?.id : undefined} presentationRunId={presentationRunId} onCitation={(c, trigger) => { citationTrigger.current = trigger; setCitation(c); }} />}
      <ChatComposer value={question} onChange={setQuestion} busy={busy} disabled={blocked || loadingOlder} onSend={send} onStop={stop} />
      <p className="chat-provider-note quiet-label">问题与相关文档片段将发送至硅基流动，模型调用可能产生费用。</p>
    </>}
    {citation ? <CitationDialog citation={citation} onDismiss={() => { setCitation(null); citationTrigger.current?.focus(); }} /> : null}
  </div>;
}
