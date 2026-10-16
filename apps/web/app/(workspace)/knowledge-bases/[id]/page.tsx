import type { Metadata } from "next";
import { DocumentWorkspace } from "@/components/documents/document-workspace";

export const metadata: Metadata = { title: "知识库文档" };

export default async function DocumentsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DocumentWorkspace key={id} knowledgeBaseId={id} />;
}
