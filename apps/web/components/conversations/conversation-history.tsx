"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, History, Plus, RefreshCw } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import type { ConversationList } from "../../../../packages/shared/types/conversation";

const labels = { streaming: "处理中", completed: "已完成", failed: "未完成", cancelled: "已停止" };

export function ConversationHistory({ knowledgeBaseId }: { knowledgeBaseId: string }) {
  const router = useRouter();
  const [data, setData] = useState<ConversationList | null>(null);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]);
    setPending(true); setError("");
    (async () => {
      const result = await apiRequest<ConversationList>(`/knowledge-bases/${knowledgeBaseId}/conversations?limit=20&offset=${offset}`, undefined, signal);
      if (controller.signal.aborted) return;
      if (offset > 0 && !result.items.length && result.total > 0) { setOffset(Math.floor((result.total - 1) / 20) * 20); return; }
      setData(result);
    })().catch((failure: unknown) => {
      if (controller.signal.aborted) return;
      if (failure instanceof ApiError && failure.status === 401) { router.replace("/login"); router.refresh(); return; }
      setError(failure instanceof Error ? failure.message : "会话加载失败");
    }).finally(() => { if (!controller.signal.aborted) setPending(false); });
    return () => controller.abort();
  }, [knowledgeBaseId, offset, revision, router]);
  return <div className="conversation-history">
    <div className="knowledge-content-toolbar"><div className="pagination-buttons">
      <button className="icon-button" aria-label="刷新历史" title="刷新历史" disabled={pending} onClick={() => setRevision((v) => v+1)}><RefreshCw size={18} /></button>
      <Link className="icon-button" aria-label="新会话" title="新会话" href={`/knowledge-bases/${knowledgeBaseId}/chat?new=1`}><Plus size={20} /></Link>
    </div></div>
    {pending ? <p role="status" className="supporting">正在加载会话…</p> : error ? <div className="list-error" role="alert"><p className="form-error">{error}</p><button className="text-button" onClick={() => setRevision((v) => v+1)}>重试</button></div>
      : !data?.items.length ? <div className="list-empty"><History size={30} aria-hidden="true" /><h2>暂无历史会话</h2></div>
      : <><div className="history-list">{data.items.map((item) => <article key={item.id} className="history-row">
        <div><Link className="history-title" href={`/knowledge-bases/${knowledgeBaseId}/chat?conversation=${item.id}`}>{item.title || "未命名会话"}</Link><p className="quiet-label">{item.last_question}</p></div>
        <div className="history-meta"><span>{item.latest_status ? labels[item.latest_status] : "暂无回答"}</span><time dateTime={item.updated_at}>{new Date(item.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}</time></div>
      </article>)}</div><div className="list-pagination"><span>共 {data.total} 个会话</span><div className="pagination-buttons">
        <button className="icon-button" aria-label="上一页会话" title="上一页会话" disabled={offset === 0} onClick={() => setOffset((v) => Math.max(0,v-20))}><ChevronLeft size={18} /></button>
        <button className="icon-button" aria-label="下一页会话" title="下一页会话" disabled={offset+20 >= data.total} onClick={() => setOffset((v) => v+20)}><ChevronRight size={18} /></button>
      </div></div></>}
  </div>;
}
