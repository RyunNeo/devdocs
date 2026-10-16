"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { ArrowLeft } from "lucide-react";
import { ApiError, apiRequest } from "@/lib/api";
import type { KnowledgeBase } from "@/lib/knowledge-bases";
import { KnowledgeBaseTabs } from "./knowledge-base-tabs";

const KnowledgeBaseContext = createContext<{
  knowledge: KnowledgeBase;
  setNavigationBusy: Dispatch<SetStateAction<boolean>>;
} | null>(null);

export function useKnowledgeBaseWorkspace() {
  const context = useContext(KnowledgeBaseContext);
  if (!context) throw new Error("Knowledge base workspace is required");
  return context;
}

export function KnowledgeBaseWorkspace({ knowledgeBaseId, children }: {
  knowledgeBaseId: string; children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [knowledge, setKnowledge] = useState<KnowledgeBase | null>(null);
  const [navigationBusy, setNavigationBusy] = useState(false);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let controller: AbortController | null = null;
    let hasLoaded = false;
    function load(background = false) {
      controller?.abort();
      const request = new AbortController();
      controller = request;
      if (!background) { setError(""); setMissing(false); }
      apiRequest<KnowledgeBase>(`/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}`, undefined,
        AbortSignal.any([request.signal, AbortSignal.timeout(10000)]))
        .then(result => {
          if (request.signal.aborted) return;
          hasLoaded = true;
          setKnowledge(result); setError(""); setMissing(false);
        })
        .catch((failure: unknown) => {
          if (request.signal.aborted) return;
          if (failure instanceof ApiError && failure.status === 401) {
            router.replace("/login"); router.refresh(); return;
          }
          const notFound = failure instanceof ApiError && failure.status === 404;
          if (notFound) { setKnowledge(null); setMissing(true); }
          // A transient background failure must not replace the current page.
          if (!background || !hasLoaded || notFound) setError(failure instanceof Error ? failure.message : "知识库加载失败");
        });
    }
    load();
    const onFocus = () => load(true);
    window.addEventListener("focus", onFocus);
    return () => { controller?.abort(); window.removeEventListener("focus", onFocus); };
  }, [knowledgeBaseId, revision, router]);

  const active = pathname.endsWith("/chat") ? "chat" : pathname.endsWith("/conversations") ? "conversations" : "documents";
  return <main className="dashboard knowledge-base-workspace">
    <header className="knowledge-base-header">
      <Link className="text-button back-link" href="/knowledge-bases" aria-disabled={navigationBusy || undefined}
        tabIndex={navigationBusy ? -1 : undefined} onClick={event => { if (navigationBusy) event.preventDefault(); }}>
        <ArrowLeft size={17} aria-hidden="true" />知识库
      </Link>
      <div className="page-heading"><div>
        <p className="eyebrow">KNOWLEDGE BASE</p>
        <h1>{knowledge?.name ?? (missing ? "知识库不存在或无法访问" : "知识库")}</h1>
        {knowledge?.description ? <p className="supporting">{knowledge.description}</p> : null}
      </div></div>
      <KnowledgeBaseTabs knowledgeBaseId={knowledgeBaseId} active={active} disabled={navigationBusy || !knowledge} />
    </header>
    {error ? <div className="list-error" role="alert"><p>{error}</p>
      {!missing ? <button className="text-button" onClick={() => setRevision(value => value + 1)}>重试</button> : null}
    </div> : knowledge ? <KnowledgeBaseContext.Provider value={{ knowledge, setNavigationBusy }}>{children}</KnowledgeBaseContext.Provider>
      : <p className="supporting" role="status">正在加载知识库…</p>}
  </main>;
}
