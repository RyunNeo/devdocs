import { KnowledgeBaseWorkspace } from "@/components/knowledge-bases/knowledge-base-workspace";

export default async function KnowledgeBaseLayout({ children, params }: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <KnowledgeBaseWorkspace key={id} knowledgeBaseId={id}>{children}</KnowledgeBaseWorkspace>;
}
