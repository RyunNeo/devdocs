import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import { BookOpen, Library, MessageSquare, UserRound, CircleCheck, CircleAlert, ArrowRight } from "lucide-react";
import { getCurrentUser } from "@/lib/auth";
import type { KnowledgeBaseList } from "@/lib/knowledge-bases";

export const metadata: Metadata = { title: "工作台" };

export default async function DashboardPage() {
  const user = await getCurrentUser();
  if (!user) return null;
  const cookieStore = await cookies();
  const cookieName = process.env.SESSION_COOKIE_NAME ?? "devdocs_session";
  const cookie = cookieStore.get(cookieName);
  const backend = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
  const [ready, overview, documentSummary] = await Promise.all([
    fetch(`${backend}/health/ready`, {
      cache: "no-store", signal: AbortSignal.timeout(7000),
    }).then((response) => response.ok).catch(() => false),
    fetch(`${backend}/knowledge-bases?limit=3&offset=0`, {
      headers: { Cookie: `${cookieName}=${cookie?.value ?? ""}` },
      cache: "no-store", signal: AbortSignal.timeout(7000),
    }).then<KnowledgeBaseList | null>((response) => response.ok ? response.json() : null).catch(() => null),
    fetch(`${backend}/documents/summary`, {
      headers: { Cookie: `${cookieName}=${cookie?.value ?? ""}` },
      cache: "no-store", signal: AbortSignal.timeout(7000),
    }).then<{ total: number } | null>((response) => response.ok ? response.json() : null).catch(() => null),
  ]);
  return (
    <main className="dashboard">
      <div className="page-heading"><div><p className="eyebrow">OVERVIEW</p><h1>学习工作台</h1><p className="supporting">你的文档与学习记录。</p></div><span className="plan-badge">个人免费版</span></div>
      <div className="stats">
        <div className="stat"><Library size={19} /><span>知识库</span><strong data-testid="knowledge-base-count">{overview?.total ?? "—"}</strong></div>
        <div className="stat"><BookOpen size={19} /><span>文档</span><strong data-testid="document-count">{documentSummary?.total ?? "—"}</strong></div>
        <div className="stat"><MessageSquare size={19} /><span>学习会话</span><strong>0</strong></div>
      </div>
      <section className="knowledge-section" aria-labelledby="knowledge-heading">
        <div className="section-heading"><h2 id="knowledge-heading">我的知识库</h2><Link href="/knowledge-bases" className="text-button">查看全部<ArrowRight size={16} aria-hidden="true" /></Link></div>
        {!overview ? <div role="alert" className="list-error"><h3>知识库暂时无法加载</h3></div> : overview.total === 0 ? <div className="empty-state"><BookOpen size={40} strokeWidth={1.3} aria-hidden="true" /><h3>暂无知识库</h3><p>这里还没有学习资料。</p></div> : <ul className="recent-knowledge-list">{overview.items.map((item) => <li key={item.id}><BookOpen size={19} aria-hidden="true" /><div><strong>{item.name}</strong><p>{item.description || "—"}</p></div></li>)}</ul>}
      </section>
      <section className="account-section" aria-labelledby="account-heading">
        <div className="section-heading"><h2 id="account-heading">账号</h2></div>
        <div className="account-row"><div className="account-icon"><UserRound size={20} /></div><div><span className="quiet-label">当前账号</span><p data-testid="account-email">{user.email}</p></div><span className="status-pill">已登录</span></div>
      </section>
      <footer className="workspace-footer">
        <span className={ready ? "service-ready" : "service-warning"}>{ready ? <CircleCheck size={15} /> : <CircleAlert size={15} />}{ready ? "服务连接正常" : "服务连接异常"}</span>
        <span>DevDocs AI</span>
      </footer>
    </main>
  );
}
