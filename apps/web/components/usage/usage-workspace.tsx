"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import type { UsageEvent, UsageEventList, UsageStatus, UsageSummary } from "../../../../packages/shared/types/usage";

const statusLabels: Record<UsageStatus, string> = {
  running: "进行中", completed: "成功", local_completed: "本地完成", failed: "失败", cancelled: "已取消", interrupted: "已中断",
};
function time(value: string) {
  const utc = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`;
  return new Date(utc).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
}
function tokens(event: UsageEvent) {
  const phases = Object.keys(event.attempts).filter(phase => event.attempts[phase] > 0);
  if (!phases.length) return "未调用";
  const values = Object.values(event.token_usage);
  const known = values.reduce((sum, value) => sum + value.known_tokens, 0);
  const incomplete = phases.some(phase => !event.token_usage[phase]?.complete);
  return incomplete ? known ? `${known.toLocaleString()}（不完整）` : "未知" : known.toLocaleString();
}

export function UsageWorkspace() {
  const router = useRouter();
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [data, setData] = useState<UsageEventList | null>(null);
  const [operation, setOperation] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]);
    const query = new URLSearchParams({ limit: "20", offset: String(offset) });
    if (operation) query.set("operation", operation);
    if (status) query.set("status", status);
    setPending(true); setError("");
    Promise.all([
      apiRequest<UsageSummary>("/usage/summary", undefined, signal),
      apiRequest<UsageEventList>(`/usage/events?${query}`, undefined, signal),
    ]).then(([nextSummary, nextData]) => {
      if (controller.signal.aborted) return;
      if (offset > 0 && !nextData.items.length) { setOffset(Math.max(0, Math.ceil(nextData.total / 20) - 1) * 20); return; }
      setSummary(nextSummary); setData(nextData); setPending(false);
    }).catch((failure: unknown) => {
      if (controller.signal.aborted) return;
      if (failure instanceof ApiError && failure.status === 401) { router.replace("/login"); router.refresh(); return; }
      setError(failure instanceof Error ? failure.message : "用量加载失败"); setPending(false);
    });
    return () => controller.abort();
  }, [operation, status, offset, revision, router]);

  return <main className="dashboard usage-workspace">
    <div className="page-heading"><div><p className="eyebrow">USAGE</p><h1>个人用量</h1></div>
      <button type="button" className="icon-button" aria-label="刷新用量" title="刷新用量" disabled={pending} onClick={() => setRevision(value => value + 1)}><RefreshCw size={18} className={pending ? "spinner" : undefined} aria-hidden="true" /></button>
    </div>
    {summary ? <>
      <section className="usage-quotas" aria-label="今日配额">{(["chat", "index"] as const).map(kind => <div key={kind} data-testid={`${kind}-quota`}>
        <h2>{kind === "chat" ? "今日问答" : "今日文档索引"}</h2>
        <p className="usage-remaining">剩余 <strong>{summary.quota[kind].remaining.toLocaleString()}</strong> 次</p>
        <p className="quiet-label">已用 {summary.quota[kind].used.toLocaleString()} / {summary.quota[kind].limit.toLocaleString()} 次</p>
        <progress aria-label={kind === "chat" ? "问答已用额度" : "索引已用额度"} max={summary.quota[kind].limit} value={Math.min(summary.quota[kind].limit, summary.quota[kind].used)} />
      </div>)}</section>
      <p className="quiet-label usage-note">重置时间：{time(summary.reset_at)}（UTC+08:00）</p>
      <section className="usage-recent" aria-label="近七日统计"><h2>近七日</h2><dl>
        <div><dt>受理任务</dt><dd>{summary.recent.total.toLocaleString()}</dd></div>
        <div><dt>成功率</dt><dd>{summary.recent.success_rate === null ? "暂无数据" : `${(summary.recent.success_rate * 100).toFixed(1)}%`}</dd></div>
        <div><dt>平均处理耗时</dt><dd>{summary.recent.avg_duration_ms === null ? "暂无数据" : `${(summary.recent.avg_duration_ms / 1000).toFixed(2)} 秒`}<small>{summary.recent.sample_count} 个完整样本</small></dd></div>
        <div><dt>已知 Token 合计</dt><dd>{summary.recent.known_tokens.toLocaleString()}<small>{summary.recent.unknown_usage_count} 个任务用量不完整</small></dd></div>
      </dl><p className="quiet-label">本地完成 {summary.recent.local_completed} · 进行中 {summary.recent.running} · 失败 {summary.recent.failed} · 取消 {summary.recent.cancelled} · 中断 {summary.recent.interrupted}</p></section>
      <p className="quiet-label usage-note">统计起始：{summary.recording_started_at ? time(summary.recording_started_at) : "暂无记录"}。次数为已受理任务；Token 缺失时标记未知，不代表供应商账单。</p>
    </> : null}
    <section className="usage-records" aria-label="调用记录" aria-busy={pending}>
      <div className="usage-filters"><label>任务类型<select aria-label="任务类型" value={operation} onChange={event => { setOperation(event.target.value); setOffset(0); }}><option value="">全部任务</option><option value="chat">问答</option><option value="index">索引</option></select></label>
        <label>任务结果<select aria-label="任务结果" value={status} onChange={event => { setStatus(event.target.value); setOffset(0); }}><option value="">全部结果</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      </div>
      {error ? <div className="list-error" role="alert"><p>{error}</p><button type="button" className="secondary-button" onClick={() => setRevision(value => value + 1)}>重试</button></div>
        : pending ? <div className="list-loading" role="status">正在加载用量…</div>
        : !data?.items.length ? <div className="list-empty"><h2>暂无调用记录</h2></div>
        : <><div className="table-scroll" role="region" aria-label="调用记录表格" tabIndex={0}><table className="knowledge-table usage-table"><caption className="sr-only">个人调用记录</caption>
          <thead><tr>{["时间", "任务", "模型", "结果", "耗时", "Token", "请求编号"].map(title => <th key={title} scope="col">{title}</th>)}</tr></thead>
          <tbody>{data.items.map(event => <tr key={event.id}><td><time dateTime={event.started_at}>{time(event.started_at)}</time></td>
            <td>{event.operation === "chat" ? "问答" : "索引"}</td><td>{Object.values(event.models).join(" / ") || "未调用"}</td>
            <td><span className={`usage-status ${event.status}`}>{statusLabels[event.status]}</span>{event.error_code ? <p className="quiet-label">{event.error_code}</p> : null}</td>
            <td>{typeof event.durations_ms.total === "number" ? `${(event.durations_ms.total / 1000).toFixed(2)} 秒` : "未知"}</td>
            <td>{tokens(event)}</td><td><code>{event.request_id}</code></td></tr>)}</tbody>
        </table></div><div className="list-pagination"><span>共 {data.total} 个任务</span><div className="pagination-buttons">
          <button type="button" className="icon-button" aria-label="上一页用量" title="上一页用量" disabled={offset === 0 || pending} onClick={() => setOffset(value => Math.max(0, value - 20))}><ChevronLeft size={18} /></button>
          <button type="button" className="icon-button" aria-label="下一页用量" title="下一页用量" disabled={pending || offset + 20 >= data.total} onClick={() => setOffset(value => value + 20)}><ChevronRight size={18} /></button>
        </div></div></>}
    </section>
  </main>;
}
