import type { Metadata } from "next";
import { KnowledgeBaseTable } from "@/components/knowledge-bases/knowledge-base-table";

export const metadata: Metadata = { title: "知识库" };

export default function KnowledgeBasesPage() {
  return (
    <main className="dashboard">
      <div className="page-heading"><div><p className="eyebrow">KNOWLEDGE BASES</p><h1>我的知识库</h1></div></div>
      <KnowledgeBaseTable />
    </main>
  );
}
