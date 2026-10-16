import type { Metadata } from "next";
import { ChatWorkspace } from "@/components/chat/chat-workspace";

export const metadata: Metadata = { title: "知识库问答" };

export default async function ChatPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ conversation?: string | string[]; new?: string | string[] }>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const conversation = typeof query.conversation === "string" ? query.conversation : null;
  const startNew = !conversation && query.new === "1";
  return <ChatWorkspace key={`${id}:${conversation ?? (startNew ? "new" : "recent")}`} knowledgeBaseId={id} initialConversation={conversation} startNew={startNew} />;
}
