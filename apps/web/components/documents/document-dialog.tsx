"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, Trash2, X } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import type { DocumentDetail, DocumentRecord } from "@/lib/documents";

export function DocumentDialog({ document, mode, onDismiss, onDeleted }: {
  document: DocumentRecord; mode: "preview" | "delete";
  onDismiss: () => void; onDeleted: () => void;
}) {
  const router = useRouter();
  const id = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const inFlight = useRef(false);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [pending, setPending] = useState(mode === "preview");
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!dialogRef.current?.open) dialogRef.current?.showModal();
    cancelRef.current?.focus();
  }, []);

  useEffect(() => {
    if (mode !== "preview") return;
    const controller = new AbortController();
    setError(""); setPending(true);
    apiRequest<DocumentDetail>(`/documents/${encodeURIComponent(document.id)}`, undefined,
      AbortSignal.any([controller.signal, AbortSignal.timeout(7000)]))
      .then((result) => { if (!controller.signal.aborted) setDetail(result); })
      .catch((failure: unknown) => {
        if (controller.signal.aborted) return;
        if (failure instanceof ApiError && failure.status === 401) {
          router.replace("/login"); router.refresh();
        } else setError(failure instanceof Error ? failure.message : "预览失败，请重试");
      }).finally(() => { if (!controller.signal.aborted) setPending(false); });
    return () => controller.abort();
  }, [document.id, mode, revision, router]);

  async function remove() {
    if (inFlight.current) return;
    inFlight.current = true; setPending(true); setError("");
    try {
      await apiRequest<void>(`/documents/${encodeURIComponent(document.id)}`, undefined, AbortSignal.timeout(15000), "DELETE");
      dialogRef.current?.close(); onDeleted();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 404) {
        dialogRef.current?.close(); onDeleted();
      } else if (failure instanceof ApiError && failure.status === 401) {
        dialogRef.current?.close(); router.replace("/login"); router.refresh();
      } else {
        setError(failure instanceof ApiError && failure.status === 0
          ? "暂时无法确认删除结果，请刷新列表确认后再重试"
          : failure instanceof Error ? failure.message : "删除失败，请重试");
        setPending(false);
      }
    } finally { inFlight.current = false; }
  }

  return (
    <dialog ref={dialogRef} className={`knowledge-dialog${mode === "preview" ? " document-preview" : ""}`}
      aria-labelledby={`${id}-title`} onClose={onDismiss}
      onCancel={(event) => { if (inFlight.current) event.preventDefault(); }}>
      <div className="dialog-heading">
        <h2 id={`${id}-title`}>{mode === "delete" ? "删除文档" : document.filename}</h2>
        <button ref={mode === "preview" ? cancelRef : undefined} className="icon-button" aria-label="关闭弹窗" title="关闭弹窗"
          disabled={mode === "delete" && pending} onClick={() => dialogRef.current?.close()}><X size={19} aria-hidden="true" /></button>
      </div>
      {mode === "delete" ? <div className="delete-confirmation" aria-busy={pending}>
        <p>确定删除文档 <strong>{document.filename}</strong>？此操作无法撤销。</p>
        {error ? <p role="alert" className="form-error">{error}</p> : null}
        <div className="dialog-actions">
          <button ref={cancelRef} className="secondary-button" disabled={pending} onClick={() => dialogRef.current?.close()}>取消</button>
          <button className="danger-button" disabled={pending} onClick={remove}>
            {pending ? <LoaderCircle size={17} className="spinner" aria-hidden="true" /> : <Trash2 size={17} aria-hidden="true" />}
            {pending ? "正在删除" : "确认删除"}
          </button>
        </div>
      </div> : <div className="preview-content" aria-busy={pending}>
        {pending ? <p role="status">正在加载文本…</p> : error ? <div role="alert"><p className="form-error">{error}</p><button className="secondary-button" onClick={() => setRevision((value) => value + 1)}>重试</button></div>
          : detail ? <><p className="quiet-label">{detail.character_count} 字符{detail.preview_truncated ? " · 预览已截断（前 20000 字符）" : ""}</p>
            {detail.error_message ? <p className="form-error">{detail.error_message}</p> : null}
            <pre>{detail.text_preview ?? "暂无解析文本"}</pre></> : null}
      </div>}
    </dialog>
  );
}
