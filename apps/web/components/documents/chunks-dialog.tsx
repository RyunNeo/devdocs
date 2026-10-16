"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import type { DocumentRecord } from "@/lib/documents";

type ChunkList = { total: number; items: {
  id: string; chunk_index: number; content: string; metadata: Record<string, unknown>;
  embedding_model: string; embedding_dimension: number;
}[] };

export function ChunksDialog({ document, onDismiss }: { document: DocumentRecord; onDismiss: () => void }) {
  const router = useRouter();
  const id = useId();
  const ref = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<ChunkList | null>(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);

  useEffect(() => { if (!ref.current?.open) ref.current?.showModal(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    setPending(true); setError("");
    apiRequest<ChunkList>(`/documents/${encodeURIComponent(document.id)}/chunks?limit=20&offset=${offset}`, undefined,
      AbortSignal.any([controller.signal, AbortSignal.timeout(7000)]))
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((failure: unknown) => {
        if (controller.signal.aborted) return;
        if (failure instanceof ApiError && failure.status === 401) { router.replace("/login"); router.refresh(); }
        else setError(failure instanceof Error ? failure.message : "片段加载失败");
      }).finally(() => { if (!controller.signal.aborted) setPending(false); });
    return () => controller.abort();
  }, [document.id, offset, revision, router]);

  return <dialog ref={ref} className="knowledge-dialog document-preview" aria-labelledby={`${id}-title`} onClose={onDismiss}>
    <div className="dialog-heading"><h2 id={`${id}-title`}>文档片段</h2><button className="icon-button" aria-label="关闭弹窗" title="关闭弹窗" onClick={() => ref.current?.close()}><X size={19} aria-hidden="true" /></button></div>
    <p className="chunk-file-name">{document.filename}</p>
    {document.index_status !== "completed" && document.chunk_count > 0 ? <p className="document-warning" role="status">上次成功索引的片段；当前索引尚未完成。</p> : null}
    {data?.items[0] ? <p className="quiet-label">{data.items[0].embedding_model} · {data.items[0].embedding_dimension} 维 · {data.total} 个片段</p> : null}
    <div className="chunk-list" aria-busy={pending}>
      {pending ? <p role="status">正在加载片段…</p> : error ? <div role="alert"><p className="form-error">{error}</p><button className="secondary-button" onClick={() => setRevision((value) => value + 1)}>重试</button></div>
        : data?.items.length ? data.items.map((chunk) => {
          const headings = Object.entries(chunk.metadata).filter(([key, value]) => key.startsWith("Header ") && typeof value === "string").map(([, value]) => String(value)).join(" / ");
          return <section key={chunk.id} className="chunk-item"><h3>片段 {chunk.chunk_index + 1}{typeof chunk.metadata.page === "number" ? ` · 第 ${chunk.metadata.page} 页` : ""}</h3>
            {headings ? <p className="quiet-label">{headings}</p> : null}<pre>{chunk.content}</pre></section>;
        }) : <p>暂无片段</p>}
    </div>
    {data && data.total > 20 ? <div className="list-pagination"><span>第 {Math.floor(offset / 20) + 1} / {Math.ceil(data.total / 20)} 页</span><div className="pagination-buttons">
      <button className="icon-button" aria-label="上一页片段" title="上一页片段" disabled={pending || offset === 0} onClick={() => setOffset((value) => Math.max(0, value - 20))}><ChevronLeft size={18} /></button>
      <button className="icon-button" aria-label="下一页片段" title="下一页片段" disabled={pending || offset + 20 >= data.total} onClick={() => setOffset((value) => value + 20)}><ChevronRight size={18} /></button>
    </div></div> : null}
  </dialog>;
}
