"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronsRight } from "lucide-react";
import type { ChatMessage, Citation } from "../../../../packages/shared/types/conversation";

type CitationHandler = (citation: Citation, trigger: HTMLButtonElement) => void;

function CompletedAnswer({ message, animate, onCitation }: { message: ChatMessage; animate: boolean; onCitation: CitationHandler }) {
  const [count, setCount] = useState(0);
  const [skipped, setSkipped] = useState(false);
  const body = useRef<HTMLParagraphElement>(null);
  const skipButton = useRef<HTMLButtonElement>(null);
  const preserveFocus = useCallback(() => {
    if (skipButton.current && document.activeElement === skipButton.current) body.current?.focus({ preventScroll: true });
  }, []);
  const characters = useMemo(() => animate
    ? Array.from(new Intl.Segmenter("zh", { granularity: "grapheme" }).segment(message.content), item => item.segment)
    : [], [animate, message.content]);
  const typing = animate && !skipped && count < characters.length;

  useEffect(() => {
    if (!animate || skipped || !characters.length) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (preference.matches) { preserveFocus(); setSkipped(true); return; }
    const onPreferenceChange = () => { if (preference.matches) { preserveFocus(); setSkipped(true); } };
    preference.addEventListener("change", onPreferenceChange);
    const started = performance.now();
    const duration = Math.min(5000, Math.max(800, characters.length * 24));
    const timer = window.setInterval(() => {
      const progress = Math.min(1, (performance.now() - started) / duration);
      if (progress === 1) preserveFocus();
      setCount(Math.floor(progress * characters.length));
      if (progress === 1) window.clearInterval(timer);
    }, 40);
    return () => { window.clearInterval(timer); preference.removeEventListener("change", onPreferenceChange); };
  }, [animate, skipped, characters, preserveFocus]);

  return <>
    <div className="chat-message-heading"><strong>DevDocs AI</strong>
      <span className={`chat-status ${typing ? "revealing" : "completed"}`} role="status">{typing ? "正在展示" : "回答完成"}</span>
      {typing ? <button ref={skipButton} type="button" className="text-button chat-reveal-all" onClick={() => { preserveFocus(); setSkipped(true); }}><ChevronsRight size={16} aria-hidden="true" />立即显示全部</button> : null}
    </div>
    <p ref={body} tabIndex={-1} className={`chat-body${typing ? " chat-typing" : ""}`} aria-busy={typing}>{typing ? characters.slice(0, count).join("") : message.content}</p>
    {!typing && message.citations.length > 0 ? <div className="chat-citations">{message.citations.map(citation => <button type="button" key={citation.number} className="chat-citation" aria-label={`查看引用 ${citation.number}`} title={`查看 ${citation.filename}`} onClick={event => onCitation(citation, event.currentTarget)}>
      [{citation.number}] {citation.filename}{typeof citation.metadata.page === "number" ? ` · 第 ${citation.metadata.page} 页` : ""}
    </button>)}</div> : null}
  </>;
}

export function MessageList({ messages, onCitation, phase, activeRunId, presentationRunId }: { messages: ChatMessage[]; onCitation: CitationHandler; phase?: "retrieving" | "generating" | "validating"; activeRunId?: string; presentationRunId?: string | null }) {
  const processing = phase === "generating" ? "正在生成" : phase === "validating" ? "正在校验" : "正在检索";
  return <div className="chat-messages" aria-label="会话消息">{messages.map((message) => <article id={`chat-message-${message.id}`} className={`chat-message ${message.role}`} key={message.id}>
    {message.role === "assistant" && message.status === "completed" ? <CompletedAnswer message={message} animate={!!presentationRunId && message.run_id === presentationRunId} onCitation={onCitation} /> : <><div className="chat-message-heading"><strong>{message.role === "user" ? "你" : "DevDocs AI"}</strong>
      {message.role === "assistant" ? <span className={`chat-status ${message.status}`} role="status">{message.status === "streaming" ? message.run_id === activeRunId ? processing : "处理中" : message.status === "completed" ? "回答完成" : message.status === "cancelled" ? "已停止" : message.error_code === "citation_invalid" ? "引用校验失败" : "回答未完成"}</span> : null}</div>
    {message.role === "user" ? <p className="chat-body">{message.content}</p> : null}
    {message.role === "assistant" && message.status === "streaming" ? <div className="chat-processing-dots" aria-hidden="true"><i /><i /><i /></div> : null}</>}
  </article>)}</div>;
}
