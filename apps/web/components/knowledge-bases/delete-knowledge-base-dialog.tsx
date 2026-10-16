"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, Trash2, X } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import type { KnowledgeBase } from "@/lib/knowledge-bases";

export function DeleteKnowledgeBaseDialog({ knowledgeBase, onDismiss, onDeleted }: {
  knowledgeBase: KnowledgeBase;
  onDismiss: () => void;
  onDeleted: (missing: boolean) => void;
}) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const inFlight = useRef(false);
  const id = useId();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!dialogRef.current?.open) dialogRef.current?.showModal();
    cancelRef.current?.focus();
  }, []);

  async function remove() {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError("");
    try {
      await apiRequest<void>(`/knowledge-bases/${encodeURIComponent(knowledgeBase.id)}`,
        undefined, AbortSignal.timeout(15000), "DELETE");
      dialogRef.current?.close();
      onDeleted(false);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 404) {
        dialogRef.current?.close();
        onDeleted(true);
      } else if (failure instanceof ApiError && failure.status === 401) {
        dialogRef.current?.close();
        router.replace("/login");
        router.refresh();
      } else {
        setError(failure instanceof ApiError && failure.status === 0
          ? "暂时无法确认删除结果，请刷新列表确认后再重试"
          : failure instanceof Error ? failure.message : "删除失败，请重试");
        setPending(false);
      }
    } finally {
      inFlight.current = false;
    }
  }

  return (
    <dialog ref={dialogRef} className="knowledge-dialog" aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-description`} onClose={onDismiss}
      onCancel={(event) => { if (inFlight.current) event.preventDefault(); }}>
      <div className="dialog-heading">
        <h2 id={`${id}-title`}>删除知识库</h2>
        <button className="icon-button" aria-label="关闭弹窗" title="关闭弹窗" disabled={pending}
          onClick={() => dialogRef.current?.close()}><X size={19} aria-hidden="true" /></button>
      </div>
      <div className="delete-confirmation" aria-busy={pending}>
        <p id={`${id}-description`}>确定删除知识库 <strong>{knowledgeBase.name}</strong> 及其全部文档？此操作无法撤销。</p>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="dialog-actions">
          <button ref={cancelRef} className="secondary-button" disabled={pending} onClick={() => dialogRef.current?.close()}>取消</button>
          <button className="danger-button" disabled={pending} onClick={remove}>
            {pending ? <LoaderCircle size={17} className="spinner" aria-hidden="true" /> : <Trash2 size={17} aria-hidden="true" />}
            {pending ? "正在删除" : "确认删除"}
          </button>
        </div>
      </div>
    </dialog>
  );
}
