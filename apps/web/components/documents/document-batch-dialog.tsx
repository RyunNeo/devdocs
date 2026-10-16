"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Database, LoaderCircle, Square, Trash2, X } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import type { DocumentRecord } from "@/lib/documents";
import { BatchServiceFailure, useDocumentBatch } from "./use-document-batch";
import { BatchResults } from "./batch-results";

export function DocumentBatchDialog({ documents, mode, onDismiss, onFinished, onBusyChange }: {
  documents: DocumentRecord[]; mode: "index" | "delete"; onDismiss: () => void;
  onFinished: () => void; onBusyChange: (busy: boolean) => void;
}) {
  const id = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const stopButton = useRef<HTMLButtonElement>(null);
  const submitting = useRef(false);
  const [started, setStarted] = useState(false);
  const batch = useDocumentBatch();
  const index = mode === "index";
  const skipReason = (doc: DocumentRecord) => index && doc.status !== "parsed" ? "文档尚未成功解析"
    : index && doc.index_status === "indexing" ? "文档正在建立索引，请稍后刷新确认" : "";

  useEffect(() => { dialog.current?.showModal(); cancelButton.current?.focus(); }, []);
  useEffect(() => {
    if (!started) return;
    if (batch.running) stopButton.current?.focus();
    else cancelButton.current?.focus();
  }, [started, batch.running]);

  async function submit() {
    if (submitting.current || started) return;
    submitting.current = true; setStarted(true); onBusyChange(true);
    try {
      const results = await batch.start(documents.map(doc => ({
        id: doc.id, label: doc.filename, skip: skipReason(doc),
        unknownMessage: `暂时无法确认${index ? "索引" : "删除"}结果，请刷新列表确认后再重试`,
        execute: async (signal: AbortSignal) => {
          if (index) {
            const result = await apiRequest<DocumentRecord>(`/documents/${encodeURIComponent(doc.id)}/index`, undefined,
              AbortSignal.any([signal, AbortSignal.timeout(120000)]), "POST");
            // The API persists provider failures as a successful HTTP response.
            if (result.index_status !== "completed") throw new BatchServiceFailure(result.index_error ?? "建立索引失败", 422);
            return `文档可检索 · ${result.chunk_count} 个片段`;
          }
          try {
            await apiRequest<void>(`/documents/${encodeURIComponent(doc.id)}`, undefined,
              AbortSignal.any([signal, AbortSignal.timeout(15000)]), "DELETE");
            return "文档及关联片段、向量已删除";
          } catch (failure) {
            if (failure instanceof ApiError && failure.status === 404) return "文档已不存在";
            throw failure;
          }
        },
      })));
      if (results) onFinished();
    } finally { submitting.current = false; onBusyChange(false); }
  }

  return <dialog ref={dialog} className="knowledge-dialog document-batch-dialog" aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`}
    onClose={onDismiss} onCancel={event => { if (submitting.current) event.preventDefault(); }}>
    <div className="dialog-heading"><h2 id={`${id}-title`}>{index ? "批量建立索引" : "批量删除文档"}</h2>
      <button type="button" className="icon-button" aria-label="关闭弹窗" title="关闭弹窗" disabled={batch.running} onClick={() => dialog.current?.close()}><X size={19} aria-hidden="true" /></button>
    </div>
    <p id={`${id}-description`}>{index ? `确认将选中的 ${documents.length} 个文档片段发送到硅基流动生成向量？服务调用可能产生费用。`
      : `确认删除选中的 ${documents.length} 个文档及关联片段、向量？此操作无法撤销。`}</p>
    {!started ? <ul className="batch-result-list batch-confirmation">{documents.map(doc => <li key={doc.id}><strong>{doc.filename}</strong>
      {skipReason(doc) ? <p className="quiet-label">将跳过：{skipReason(doc)}</p> : null}</li>)}</ul> : null}
    <BatchResults results={batch.results} running={batch.running} label={index ? "索引结果" : "删除结果"} />
    <div className="dialog-actions">
      {batch.running ? <button ref={stopButton} type="button" className="secondary-button" disabled={batch.stopping} onClick={batch.stop}><Square size={15} aria-hidden="true" />{batch.stopping ? "等待当前文档完成" : "停止后续任务"}</button>
        : <button ref={cancelButton} type="button" className="secondary-button" onClick={() => dialog.current?.close()}>{started ? "关闭" : "取消"}</button>}
      {!started ? <button type="button" className={index ? "primary-button" : "danger-button"} disabled={!documents.some(doc => !skipReason(doc))} onClick={() => void submit()}>
        {index ? <Database size={17} aria-hidden="true" /> : <Trash2 size={17} aria-hidden="true" />}{index ? "确认建立索引" : "确认删除"}
      </button> : batch.running ? <LoaderCircle className="spinner" size={20} aria-label="批量处理中" /> : null}
    </div>
  </dialog>;
}
