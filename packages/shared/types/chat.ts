import type { Citation } from "./conversation";
export type ChatEvent =
  | { event: "meta"; data: { conversation_id: string; run_id: string; assistant_message_id: string; user_sequence?: number } }
  | { event: "token"; data: { delta: string } }
  | { event: "status"; data: { phase: "retrieving" | "generating" | "validating" } }
  | { event: "citations"; data: { items: Citation[] } }
  | { event: "done"; data: { message_id: string; status: "completed"; content?: string; usage: Record<string, number> | null } }
  | { event: "error"; data: { code: string; message: string; message_id?: string } };
