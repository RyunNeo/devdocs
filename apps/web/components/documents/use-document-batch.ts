"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";

export type BatchState = "waiting" | "running" | "succeeded" | "failed" | "unknown" | "skipped" | "stopped";
export type BatchResult = { id: string; label: string; state: BatchState; detail: string };
export type BatchTask = { id: string; label: string; skip?: string; unknownMessage: string; execute: (signal: AbortSignal) => Promise<string> };

export class BatchServiceFailure extends ApiError {}

export function useDocumentBatch() {
  const router = useRouter();
  const [results, setResults] = useState<BatchResult[]>([]);
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);
  const inFlight = useRef(false);
  const stopped = useRef(false);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; stopped.current = true; controller.current?.abort(); };
  }, []);

  async function start(tasks: BatchTask[]): Promise<BatchResult[] | null> {
    if (inFlight.current) return null;
    inFlight.current = true; stopped.current = false;
    setRunning(true); setStopping(false);
    const rows: BatchResult[] = tasks.map(task => ({ id: task.id, label: task.label, state: task.skip ? "skipped" : "waiting", detail: task.skip ?? "" }));
    const publish = () => { if (mounted.current) setResults(rows.map(row => ({ ...row }))); };
    publish();
    try {
      for (let i = 0; i < tasks.length; i++) {
        if (tasks[i].skip) continue;
        if (stopped.current) { rows[i].state = "stopped"; rows[i].detail = "未执行"; publish(); continue; }
        rows[i].state = "running"; publish();
        const request = new AbortController(); controller.current = request;
        try {
          rows[i].detail = await tasks[i].execute(request.signal);
          rows[i].state = "succeeded";
        } catch (failure) {
          const uncertain = !(failure instanceof ApiError) || failure.status === 0 || failure.status >= 500;
          rows[i].state = uncertain ? "unknown" : "failed";
          rows[i].detail = uncertain ? tasks[i].unknownMessage : failure instanceof Error ? failure.message : "操作失败";
          if (uncertain || failure instanceof BatchServiceFailure || (failure instanceof ApiError && [401, 403, 429].includes(failure.status))) stopped.current = true;
          if (failure instanceof ApiError && failure.status === 401 && mounted.current) { router.replace("/login"); router.refresh(); }
        }
        publish();
      }
      return mounted.current ? rows : null;
    } finally {
      controller.current = null; inFlight.current = false;
      if (mounted.current) { setRunning(false); setStopping(false); }
    }
  }

  function stop() { stopped.current = true; setStopping(true); }
  function reset() { if (!inFlight.current) { setResults([]); setStopping(false); } }
  return { results, running, stopping, start, stop, reset };
}
