import { Brand } from "@/components/ui/brand";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth-shell">
      <header className="auth-header"><Brand /><span className="quiet-label">开发者学习工作台</span></header>
      <main className="auth-main">{children}</main>
      <footer className="auth-footer"><span>DevDocs AI</span><span>读懂文档，积累知识。</span></footer>
    </div>
  );
}
