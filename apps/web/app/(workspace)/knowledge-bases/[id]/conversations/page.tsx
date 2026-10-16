import type { Metadata } from "next";
import { ConversationHistory } from "@/components/conversations/conversation-history";

export const metadata: Metadata = { title: "历史会话" };
export default async function HistoryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ConversationHistory key={id} knowledgeBaseId={id} />;
}
