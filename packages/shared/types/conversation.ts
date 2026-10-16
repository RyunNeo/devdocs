export type Citation = {
  number: number; document_id: string; chunk_id: string; chunk_index: number;
  filename: string; content: string; metadata: Record<string, unknown>;
  source_status: "current" | "changed" | "deleted"; index_fingerprint: string;
};
export type ChatMessage = {
  id: string; role: "user" | "assistant"; content: string;
  status: "streaming" | "completed" | "failed" | "cancelled";
  run_id: string | null; sequence: number; citations: Citation[];
  error_code: string | null; model?: string | null; usage?: Record<string, number> | null;
};
export type ConversationDetail = {
  id: string; knowledge_base_id: string; messages: ChatMessage[]; has_older: boolean;
};
export type ConversationSummary = {
  id: string; knowledge_base_id: string; title: string; last_question: string;
  latest_status: ChatMessage["status"] | null; created_at: string; updated_at: string;
};
export type ConversationList = { items: ConversationSummary[]; total: number; limit: number; offset: number };
