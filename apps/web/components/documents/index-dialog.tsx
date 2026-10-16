"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Database, LoaderCircle, X } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import type { DocumentRecord } from "@/lib/documents";

export function IndexDialog({ document, onDismiss, onFinished }: {
  document: DocumentRecord; onDismiss: () => void; onFinished: (result?: DocumentRecord) => void;
}) {
  const router = useRouter();
  const id = useId();
  const ref = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ref.current?.open) ref.current?.showModal();
    cancelRef.current?.focus();
  }, []);

  async function submit() {
    if (inFlight.current) return;
    inFlight.current = true; setPending(true); setError("");
    try {
      const result = await apiRequest<DocumentRecord>(`/documents/${encodeURIComponent(document.id)}/index`, undefined, AbortSignal.timeout(120000), "POST");
      ref.current?.close(); onFinished(result);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        ref.current?.close(); router.replace("/login"); router.refresh();
      } else if (failure instanceof ApiError && failure.status === 404) {
        ref.current?.close(); onFinished();
      } else {
        setError(failure instanceof ApiError && failure.status === 0
          ? "暂时无法确认索引结果，请刷新列表确认后再重试"
          : failure instanceof Error ? failure.message : "建立索引失败");
        setPending(false);
      }
    } finally { inFlight.current = false; }
  }

  return <dialog ref={ref} className="knowledge-dialog" aria-labelledby={`${id}-title`} aria-describedby={`${id}-details`}
    onClose={onDismiss} onCancel={(event) => { if (inFlight.current) event.preventDefault(); }}>
    <div className="dialog-heading"><h2 id={`${id}-title`}>建立文档索引</h2>
      <button className="icon-button" aria-label="关闭弹窗" title="关闭弹窗" disabled={pending} onClick={() => ref.current?.close()}><X size={19} aria-hidden="true" /></button></div>
    <div className="delete-confirmation" aria-busy={pending}>
      <p id={`${id}-details`}>确认将 <strong>{document.filename}</strong> 的文档片段发送到硅基流动生成向量？服务调用可能产生费用。</p>
      <p className="quiet-label">BAAI/bge-m3 · 1024 维</p>
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      <div className="dialog-actions"><button ref={cancelRef} className="secondary-button" disabled={pending} onClick={() => ref.current?.close()}>取消</button>
        <button className="primary-button" disabled={pending} onClick={submit}>{pending ? <LoaderCircle size={17} className="spinner" aria-hidden="true" /> : <Database size={17} aria-hidden="true" />}{pending ? "正在建立索引" : "确认建立索引"}</button></div>
    </div>
  </dialog>;
}
