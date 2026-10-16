"use client";
import Link from "next/link";
import { Files, History, MessageSquare } from "lucide-react";

export function KnowledgeBaseTabs({ knowledgeBaseId, active, disabled = false }: {
  knowledgeBaseId: string; active: "documents" | "chat" | "conversations"; disabled?: boolean;
}) {
  const base = `/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}`;
  const tabs = [
    { key: "documents", href: base, label: "文档", Icon: Files },
    { key: "chat", href: `${base}/chat`, label: "问答", Icon: MessageSquare },
    { key: "conversations", href: `${base}/conversations`, label: "历史会话", Icon: History },
  ];
  return <nav className="knowledge-tabs" aria-label="知识库页面">{tabs.map(({ key, href, label, Icon }) =>
    <Link key={key} href={href} scroll={false} aria-disabled={disabled || undefined} tabIndex={disabled ? -1 : undefined}
      onClick={event => { if (disabled) event.preventDefault(); }}
      aria-current={key === active ? "page" : undefined} className={key === active ? "active" : undefined}><Icon size={16} aria-hidden="true" />{label}</Link>
  )}</nav>;
}
