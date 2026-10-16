"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, Gauge, LayoutDashboard } from "lucide-react";

export function WorkspaceNavigation() {
  const pathname = usePathname();
  return (
    <nav aria-label="工作台导航">
      {[
        { href: "/dashboard", label: "概览", Icon: LayoutDashboard },
        { href: "/knowledge-bases", label: "知识库", Icon: BookOpen },
        { href: "/settings/usage", label: "用量", Icon: Gauge },
      ].map(({ href, label, Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return <Link key={href} href={href} aria-current={active ? "page" : undefined} className={`nav-item${active ? " active" : ""}`}><Icon size={18} aria-hidden="true" />{label}</Link>;
      })}
    </nav>
  );
}

export function WorkspaceBreadcrumb() {
  const pathname = usePathname();
  return <span className="breadcrumb">工作空间 <span>/</span> {pathname.startsWith("/knowledge-bases") ? "知识库" : pathname.startsWith("/settings/usage") ? "用量" : "概览"}</span>;
}
