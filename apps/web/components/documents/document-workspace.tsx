"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Database, FileText, Layers3, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useKnowledgeBaseWorkspace } from "@/components/knowledge-bases/knowledge-base-workspace";
import { ApiError, apiRequest } from "@/lib/api";
import { documentStatuses, indexStatuses, type DocumentList, type DocumentRecord } from "@/lib/documents";
import { UploadForm } from "@/components/documents/upload-form";
import { DocumentDialog } from "@/components/documents/document-dialog";
import { IndexDialog } from "@/components/documents/index-dialog";
import { ChunksDialog } from "@/components/documents/chunks-dialog";
import { DocumentBatchDialog } from "@/components/documents/document-batch-dialog";

const pageSize = 20;

export function DocumentWorkspace({ knowledgeBaseId }: { knowledgeBaseId: string }) {
  const router = useRouter();
  const { knowledge, setNavigationBusy } = useKnowledgeBaseWorkspace();
  const [data, setData] = useState<DocumentList | null>(null);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [retrying, setRetrying] = useState<string | null>(null);
  const retryInFlight = useRef(false);
  const [dialog, setDialog] = useState<{ document: DocumentRecord; mode: "preview" | "delete" } | null>(null);
  const [indexing, setIndexing] = useState<DocumentRecord | null>(null);
  const [chunks, setChunks] = useState<DocumentRecord | null>(null);
  const refreshButton = useRef<HTMLButtonElement>(null);
  const focusAfterRefresh = useRef(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [uploadBusy, setUploadBusy] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchDialog, setBatchDialog] = useState<{ mode: "index" | "delete"; documents: DocumentRecord[] } | null>(null);
  const selectAll = useRef<HTMLInputElement>(null);
  const controlsLocked = retrying !== null || uploadBusy || batchDialog !== null;

  useEffect(() => {
    setNavigationBusy(uploadBusy || batchBusy);
    return () => setNavigationBusy(false);
  }, [uploadBusy, batchBusy, setNavigationBusy]);

  useEffect(() => {
    if (selectAll.current) selectAll.current.indeterminate = selected.size > 0 && selected.size < (data?.items.length ?? 0);
  }, [selected, data]);

  useEffect(() => {
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(7000)]);
    setPending(true); setError(""); setMissing(false); setSelected(new Set());
    apiRequest<DocumentList>(`/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/documents?limit=${pageSize}&offset=${offset}`, undefined, signal).then((result) => {
      if (controller.signal.aborted) return;
      if (offset > 0 && result.items.length === 0) {
        setOffset(Math.max(0, Math.ceil(result.total / pageSize) - 1) * pageSize);
        return;
      }
      setData(result); setPending(false);
    }).catch((failure: unknown) => {
      if (controller.signal.aborted) return;
      if (failure instanceof ApiError && failure.status === 401) {
        router.replace("/login"); router.refresh(); return;
      }
      setMissing(failure instanceof ApiError && failure.status === 404);
      setError(failure instanceof Error ? failure.message : "文档加载失败，请重试");
      setPending(false);
    });
    return () => controller.abort();
  }, [knowledgeBaseId, offset, revision, router]);

  useEffect(() => {
    if (!pending && focusAfterRefresh.current) {
      refreshButton.current?.focus(); focusAfterRefresh.current = false;
    }
  }, [pending, data, error]);

  function refresh(resetPage = false, restoreFocus = false) {
    setActionError("");
    focusAfterRefresh.current = restoreFocus;
    setPending(true);
    if (resetPage) setOffset(0);
    setRevision((value) => value + 1);
    router.refresh();
  }

  async function retry(doc: DocumentRecord) {
    if (retryInFlight.current) return;
    retryInFlight.current = true; setRetrying(doc.id); setActionError("");
    try {
      const result = await apiRequest<DocumentRecord>(`/documents/${encodeURIComponent(doc.id)}/retry`, undefined, AbortSignal.timeout(30000), "POST");
      setNotice(result.status === "parsed" ? "文档已解析" : "解析失败，已更新失败原因");
      refresh(false, true);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        router.replace("/login"); router.refresh();
      } else if (failure instanceof ApiError && failure.status === 404) {
        setNotice("文档已不存在，已重新加载列表"); refresh(false, true);
      } else {
        setActionError(failure instanceof ApiError && failure.status === 0
          ? "暂时无法确认解析结果，请刷新列表确认后再重试"
          : failure instanceof Error ? failure.message : "重新解析失败");
      }
    } finally { retryInFlight.current = false; setRetrying(null); }
  }

  if (missing) return <div className="list-error" role="alert"><h2>知识库不存在或无法访问</h2></div>;

  return (
    <div className="document-workspace">
      {knowledge ? <UploadForm knowledgeBaseId={knowledgeBaseId} disabled={controlsLocked || !!error} onBusyChange={setUploadBusy} onUploaded={(docs) => {
        setNotice(docs.length === 1 ? docs[0].status === "parsed" ? "文档已上传并解析" : "文档已保存，解析失败，请查看失败原因" : docs.length ? `已保存 ${docs.length} 个文档` : "上传任务已结束，请查看逐文件结果");
        refresh(true);
      }} /> : null}
      <section className="knowledge-list" aria-label="文档列表" aria-busy={pending}>
        <div className="list-toolbar"><span role="status" className="quiet-label">{data && !error ? `${data.total} 个文档` : pending ? "加载中" : "加载失败"}</span>
          <button ref={refreshButton} className="icon-button" aria-label="刷新文档" title="刷新文档" disabled={pending || controlsLocked}
            onClick={() => refresh()}><RefreshCw size={17} className={pending ? "spinner" : undefined} aria-hidden="true" /></button></div>
        {notice ? <p className="list-notice" role="status">{notice}</p> : null}
        {actionError ? <p className="form-error" role="alert">{actionError}</p> : null}
        {selected.size > 0 ? <div className="document-batch-toolbar"><span role="status">已选择 {selected.size} 个文档</span>
          <button type="button" className="secondary-button" disabled={pending || controlsLocked} onClick={() => setBatchDialog({ mode: "index", documents: data!.items.filter(doc => selected.has(doc.id)) })}><Database size={16} aria-hidden="true" />批量建立索引</button>
          <button type="button" className="secondary-button delete-trigger" disabled={pending || controlsLocked} onClick={() => setBatchDialog({ mode: "delete", documents: data!.items.filter(doc => selected.has(doc.id)) })}><Trash2 size={16} aria-hidden="true" />批量删除</button>
          <button type="button" className="text-button" disabled={pending || controlsLocked} onClick={() => setSelected(new Set())}>取消选择</button>
        </div> : null}
        {error ? <div className="list-error" role="alert"><h2>文档加载失败</h2><p>{error}</p></div>
          : <div className="table-scroll" role="region" aria-label="文档表格" tabIndex={0}>
            <table className="document-table"><caption className="sr-only">知识库文档</caption>
              <colgroup><col className="document-name-column" /><col className="document-size-column" /><col className="document-state-column" /><col className="document-action-column" /></colgroup>
              <thead><tr><th scope="col"><label className="document-selection"><input ref={selectAll} type="checkbox" aria-label="全选当前页" disabled={pending || controlsLocked || !data?.items.length}
                checked={!!data?.items.length && selected.size === data.items.length} onChange={event => setSelected(new Set(event.target.checked ? data?.items.map(doc => doc.id) : []))} />文档</label></th><th scope="col">大小</th><th scope="col">解析状态</th><th scope="col" className="knowledge-actions">操作</th></tr></thead>
              <tbody>{pending ? <tr><td colSpan={4}><div className="list-loading" role="status">正在加载文档…</div></td></tr>
                : data?.items.length ? data.items.map((doc) => <tr key={doc.id}>
                  <td><label className="document-selection"><input type="checkbox" aria-label={`选择 ${doc.filename}`} checked={selected.has(doc.id)} disabled={pending || controlsLocked} onChange={event => setSelected(previous => {
                    const next = new Set(previous); if (event.target.checked) next.add(doc.id); else next.delete(doc.id); return next;
                  })} /><strong>{doc.filename}</strong></label><p className="quiet-label">{doc.file_type.toUpperCase()}{doc.status === "parsed" ? ` · ${doc.character_count} 字符` : ""}</p>
                    <div className="document-mobile-status"><span className={`document-state ${doc.status}`}>{retrying === doc.id ? "解析中" : documentStatuses[doc.status]}</span>
                      {doc.status === "parsed" ? <p className={`document-index-status ${doc.index_status}`}>{indexStatuses[doc.index_status]}{doc.chunk_count ? ` · ${doc.chunk_count} 个片段` : ""}</p> : null}
                      {doc.index_error ? <p className="document-failure">{doc.index_error}</p> : null}
                      {doc.parse_warning ? <p className="document-warning">{doc.parse_warning}</p> : null}
                      {doc.error_message ? <p className="document-failure">{doc.error_message}</p> : null}</div></td>
                  <td className="quiet-label">{(doc.size_bytes / 1024).toFixed(1)} KiB</td>
                  <td><span className={`document-state ${doc.status}`}>{retrying === doc.id ? "解析中" : documentStatuses[doc.status]}</span>
                    {doc.status === "parsed" ? <p className={`document-index-status ${doc.index_status}`}>{indexStatuses[doc.index_status]}{doc.chunk_count ? ` · ${doc.chunk_count} 个片段` : ""}</p> : null}
                    {doc.index_error ? <p className="document-failure">{doc.index_error}</p> : null}
                    {doc.parse_warning ? <p className="document-warning">{doc.parse_warning}</p> : null}
                    {doc.error_message ? <p className="document-failure">{doc.error_message}</p> : null}</td>
                  <td className="knowledge-actions"><div className="document-row-actions">
                    {doc.status === "parsed" ? <><button className="icon-button" aria-label={`预览 ${doc.filename}`} title={`预览 ${doc.filename}`} disabled={controlsLocked} onClick={() => setDialog({ document: doc, mode: "preview" })}><FileText size={17} aria-hidden="true" /></button>
                      <button className="icon-button" aria-label={`建立索引 ${doc.filename}`} title={`建立索引 ${doc.filename}`} disabled={controlsLocked} onClick={() => setIndexing(doc)}><Database size={17} aria-hidden="true" /></button>
                      <button className="icon-button" aria-label={`查看片段 ${doc.filename}`} title={`查看片段 ${doc.filename}`} disabled={doc.chunk_count === 0 || controlsLocked} onClick={() => setChunks(doc)}><Layers3 size={17} aria-hidden="true" /></button></> : null}
                    {doc.status !== "parsed" ? <button className="icon-button" aria-label={`重新解析 ${doc.filename}`} title={`重新解析 ${doc.filename}`} disabled={controlsLocked} onClick={() => retry(doc)}><RotateCcw size={17} className={retrying === doc.id ? "spinner" : undefined} aria-hidden="true" /></button> : null}
                    <button className="icon-button delete-trigger" aria-label={`删除 ${doc.filename}`} title={`删除 ${doc.filename}`} disabled={controlsLocked} onClick={() => setDialog({ document: doc, mode: "delete" })}><Trash2 size={17} aria-hidden="true" /></button>
                  </div></td>
                </tr>) : <tr><td colSpan={4}><div className="list-empty"><FileText size={32} aria-hidden="true" /><h2>暂无文档</h2></div></td></tr>}</tbody>
            </table>
          </div>}
        {data && !error && data.total > 0 ? <div className="list-pagination"><span>第 {Math.floor(offset / pageSize) + 1} / {Math.ceil(data.total / pageSize)} 页</span>
          <div className="pagination-buttons"><button className="icon-button" aria-label="上一页" title="上一页" disabled={pending || controlsLocked || offset === 0} onClick={() => setOffset((value) => Math.max(0, value - pageSize))}><ChevronLeft size={18} /></button>
            <button className="icon-button" aria-label="下一页" title="下一页" disabled={pending || controlsLocked || offset + pageSize >= data.total} onClick={() => setOffset((value) => value + pageSize)}><ChevronRight size={18} /></button></div></div> : null}
      </section>
      {dialog ? <DocumentDialog key={`${dialog.document.id}-${dialog.mode}`} {...dialog} onDismiss={() => setDialog(null)} onDeleted={() => {
        setDialog(null); setNotice("文档已删除"); refresh(false, true);
      }} /> : null}
      {indexing ? <IndexDialog key={indexing.id} document={indexing} onDismiss={() => setIndexing(null)} onFinished={(result) => {
        setIndexing(null); setNotice(result ? result.index_status === "completed" ? "索引已完成，文档可检索" : "索引失败，请查看失败原因" : "文档已不存在，已刷新列表"); refresh(false, true);
      }} /> : null}
      {chunks ? <ChunksDialog key={chunks.id} document={chunks} onDismiss={() => setChunks(null)} /> : null}
      {batchDialog ? <DocumentBatchDialog {...batchDialog} onBusyChange={setBatchBusy} onFinished={() => refresh(false)} onDismiss={() => {
        setBatchDialog(null); refreshButton.current?.focus();
      }} /> : null}
    </div>
  );
}
