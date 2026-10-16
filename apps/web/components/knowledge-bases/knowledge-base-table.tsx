"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BookOpen, ChevronLeft, ChevronRight, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import type { KnowledgeBase, KnowledgeBaseList } from "@/lib/knowledge-bases";
import { KnowledgeBaseDialog } from "@/components/knowledge-bases/knowledge-base-dialog";
import { DeleteKnowledgeBaseDialog } from "@/components/knowledge-bases/delete-knowledge-base-dialog";

const pageSize = 20;
const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hour12: false,
});

function Timestamp({ value }: { value: string }) {
  // Database test adapters can return UTC timestamps without a timezone suffix.
  const instant = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`;
  return <time dateTime={instant} title={value}>{dateFormatter.format(new Date(instant))}</time>;
}

export function KnowledgeBaseTable() {
  const router = useRouter();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<KnowledgeBaseList | null>(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<KnowledgeBase | null>(null);
  const [deleting, setDeleting] = useState<KnowledgeBase | null>(null);
  const [notice, setNotice] = useState("");
  const editButtons = useRef(new Map<string, HTMLButtonElement>());
  const refreshButton = useRef<HTMLButtonElement>(null);
  const savedFocusId = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setPending(true);
    setError("");
    apiRequest<KnowledgeBaseList>(
      `/knowledge-bases?limit=${pageSize}&offset=${offset}`,
      undefined,
      AbortSignal.any([controller.signal, AbortSignal.timeout(7000)]),
    ).then((result) => {
      if (controller.signal.aborted) return;
      if (offset > 0 && result.items.length === 0) {
        setOffset(Math.max(0, Math.ceil(result.total / pageSize) - 1) * pageSize);
        return;
      }
      setData(result);
      setPending(false);
    }).catch((failure: unknown) => {
      if (controller.signal.aborted) return;
      if (failure instanceof ApiError && failure.status === 401) {
        router.replace("/login");
        router.refresh();
        return;
      }
      setError(failure instanceof Error ? failure.message : "知识库加载失败，请重试");
      setPending(false);
    });
    return () => controller.abort();
  }, [offset, revision, router]);

  useEffect(() => {
    if (!pending && savedFocusId.current) {
      (editButtons.current.get(savedFocusId.current) ?? refreshButton.current)?.focus();
      savedFocusId.current = null;
    }
  }, [pending, data, error]);

  return (
    <section className="knowledge-list" aria-label="知识库列表" aria-busy={pending}>
      <div className="list-toolbar">
        <span className="quiet-label" role="status">{data && !error ? `${data.total} 个知识库` : pending ? "加载中" : "加载失败"}</span>
        <div className="list-toolbar-actions">
          <button ref={refreshButton} className="icon-button" aria-label="刷新知识库" title="刷新知识库" disabled={pending} onClick={() => setRevision((value) => value + 1)}><RefreshCw size={17} className={pending ? "spinner" : undefined} aria-hidden="true" /></button>
          <button className="primary-button create-trigger" onClick={() => setShowCreate(true)}><Plus size={17} aria-hidden="true" />创建知识库</button>
        </div>
      </div>
      {notice ? <p role="status" className="list-notice">{notice}</p> : null}
      {error ? <div role="alert" className="list-error"><h2>知识库加载失败</h2><p>{error}</p></div> : (
        <div className="table-scroll" role="region" aria-label="知识库表格" tabIndex={0}>
          <table className="knowledge-table">
            <caption className="sr-only">我的知识库</caption>
            <colgroup><col className="name-column" /><col className="description-column" /><col className="date-column" /><col className="date-column" /><col className="action-column" /></colgroup>
            <thead><tr><th scope="col">名称</th><th scope="col">描述</th><th scope="col">创建时间</th><th scope="col">更新时间</th><th scope="col" className="knowledge-actions">操作</th></tr></thead>
            <tbody>
              {pending ? <tr><td colSpan={5}><div className="list-loading" role="status">正在加载知识库…</div></td></tr> : data?.items.length ? data.items.map((item) => (
                <tr key={item.id}>
                  <td className="knowledge-name"><Link className="knowledge-link" href={`/knowledge-bases/${item.id}`}>{item.name}</Link></td>
                  <td><span className="knowledge-description" title={item.description ?? undefined}>{item.description || "—"}</span></td>
                  <td className="knowledge-date"><Timestamp value={item.created_at} /></td>
                  <td className="knowledge-date"><Timestamp value={item.updated_at} /></td>
                  <td className="knowledge-actions"><button ref={(node) => {
                    if (node) editButtons.current.set(item.id, node);
                    else editButtons.current.delete(item.id);
                  }} className="icon-button" aria-label={`编辑 ${item.name}`} title={`编辑 ${item.name}`} onClick={() => setEditing(item)}><Pencil size={17} aria-hidden="true" /></button>
                  <button className="icon-button delete-trigger" aria-label={`删除 ${item.name}`} title={`删除 ${item.name}`}
                    onClick={() => { setNotice(""); setDeleting(item); }}><Trash2 size={17} aria-hidden="true" /></button></td>
                </tr>
              )) : <tr><td colSpan={5}><div className="list-empty"><BookOpen size={32} strokeWidth={1.4} aria-hidden="true" /><h2>暂无知识库</h2></div></td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {data && !error && data.total > 0 ? <div className="list-pagination">
        <span>第 {Math.floor(offset / pageSize) + 1} / {Math.ceil(data.total / pageSize)} 页</span>
        <div className="pagination-buttons">
          <button className="icon-button" aria-label="上一页" title="上一页" disabled={pending || offset === 0} onClick={() => setOffset((value) => Math.max(0, value - pageSize))}><ChevronLeft size={18} /></button>
          <button className="icon-button" aria-label="下一页" title="下一页" disabled={pending || offset + pageSize >= data.total} onClick={() => setOffset((value) => value + pageSize)}><ChevronRight size={18} /></button>
        </div>
      </div> : null}
      {showCreate || editing ? <KnowledgeBaseDialog key={editing?.id ?? "create"} knowledgeBase={editing ?? undefined} onDismiss={() => {
        setShowCreate(false); setEditing(null);
      }} onSaved={() => {
        savedFocusId.current = editing?.id ?? null;
        setShowCreate(false);
        setEditing(null);
        setPending(true);
        setOffset(0);
        setRevision((value) => value + 1);
        router.refresh();
      }} /> : null}
      {deleting ? <DeleteKnowledgeBaseDialog key={deleting.id} knowledgeBase={deleting}
        onDismiss={() => setDeleting(null)} onDeleted={(missing) => {
          savedFocusId.current = deleting.id;
          setDeleting(null);
          setNotice(missing ? "知识库已不存在，已重新加载列表" : "知识库已删除");
          setPending(true);
          setRevision((value) => value + 1);
          router.refresh();
        }} /> : null}
    </section>
  );
}
