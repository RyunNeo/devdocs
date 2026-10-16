export type DocumentRecord = {
  id: string;
  knowledge_base_id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  status: "pending" | "processing" | "parsed" | "failed";
  error_message: string | null;
  parse_warning: string | null;
  character_count: number;
  index_status: "pending" | "indexing" | "completed" | "failed";
  index_error: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
};

export type DocumentList = { items: DocumentRecord[]; total: number; limit: number; offset: number };
export type DocumentDetail = DocumentRecord & { text_preview: string | null; preview_truncated: boolean };
export const documentStatuses = { pending: "待解析", processing: "解析中", parsed: "已解析", failed: "解析失败" };
export const indexStatuses = { pending: "未建索引", indexing: "索引中", completed: "可检索", failed: "索引失败" };
