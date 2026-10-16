import type { BatchResult, BatchState } from "./use-document-batch";

const labels: Record<BatchState, string> = { waiting: "待处理", running: "处理中", succeeded: "成功", failed: "失败", unknown: "结果待确认", skipped: "已跳过", stopped: "已停止" };

export function BatchResults({ results, running, label }: { results: BatchResult[]; running: boolean; label: string }) {
  if (!results.length) return null;
  const finished = results.filter(row => row.state !== "waiting" && row.state !== "running").length;
  return <section className="batch-results" aria-label={label}>
    <div className="batch-summary" role="status">
      <span>{running ? `已处理 ${finished} / ${results.length}` : `已结束 ${finished} / ${results.length}`}</span>
      {(["succeeded", "failed", "unknown", "skipped", "stopped"] as const).map(state => {
        const count = results.filter(row => row.state === state).length;
        return count ? <span key={state} className={`batch-state ${state}`}>{labels[state]} {count}</span> : null;
      })}
    </div>
    <progress max={results.length} value={finished} aria-label={`${label}进度`} />
    <ul className="batch-result-list">{results.map(row => <li key={row.id}>
      <div className="batch-result-heading"><strong>{row.label}</strong><span className={`batch-state ${row.state}`}>{labels[row.state]}</span></div>
      {row.detail ? <p className="quiet-label" role={row.state === "failed" || row.state === "unknown" ? "alert" : undefined}>{row.detail}</p> : null}
    </li>)}</ul>
  </section>;
}
