"use client";
import { useEffect, useId, useRef } from "react";
import { X } from "lucide-react";
import type { Citation } from "../../../../packages/shared/types/conversation";

export function CitationDialog({ citation, onDismiss }: { citation: Citation; onDismiss: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => { ref.current?.showModal(); }, []);
  const headings = Object.entries(citation.metadata).filter(([key, value]) => key.startsWith("Header ") && typeof value === "string").map(([, value]) => String(value)).join(" / ");
  return <dialog ref={ref} className="knowledge-dialog document-preview" aria-labelledby={id} onClose={onDismiss}>
    <div className="dialog-heading"><h2 id={id}>引用原文</h2><button className="icon-button" aria-label="关闭引用" title="关闭引用" onClick={() => ref.current?.close()} autoFocus><X size={19} /></button></div>
    <p className="chunk-file-name">[{citation.number}] {citation.filename}</p>
    <p className="quiet-label">片段 {citation.chunk_index + 1}{typeof citation.metadata.page === "number" ? ` · 第 ${citation.metadata.page} 页` : ""}{headings ? ` · ${headings}` : ""}</p>
    {citation.source_status !== "current" ? <p className="document-warning">{citation.source_status === "deleted" ? "原文已删除；以下为回答时的快照。" : "原文索引已变化；以下为回答时的快照。"}</p> : null}
    <div className="chunk-list"><pre className="chat-source">{citation.content}</pre></div>
  </dialog>;
}
