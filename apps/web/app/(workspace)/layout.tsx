import { redirect } from "next/navigation";
import { CircleHelp } from "lucide-react";
import { Brand } from "@/components/ui/brand";
import { LogoutButton } from "@/components/auth/logout-button";
import { getCurrentUser } from "@/lib/auth";
import { WorkspaceBreadcrumb, WorkspaceNavigation } from "@/components/ui/workspace-navigation";

export default async function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  let user;
  try {
    user = await getCurrentUser();
  } catch {
    return (
      <main className="connection-error">
        <Brand />
        <h1>暂时无法连接工作台</h1>
        <p>服务暂不可用，请稍后重试。</p>
        <a href="/dashboard" className="primary-button">重试</a>
      </main>
    );
  }
  if (!user) redirect("/login");
  return (
    <div className="workspace">
      <aside className="sidebar">
        <Brand />
        <p className="nav-label">工作空间</p>
        <WorkspaceNavigation />
        <div className="sidebar-bottom"><CircleHelp size={16} /><span>DevDocs AI · 个人空间</span></div>
      </aside>
      <div className="workspace-main">
        <header className="workspace-header">
          <WorkspaceBreadcrumb />
          <LogoutButton />
        </header>
        {children}
      </div>
    </div>
  );
}
