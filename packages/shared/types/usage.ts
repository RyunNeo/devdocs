export type UsageOperation = "chat" | "index";
export type UsageStatus = "running" | "completed" | "local_completed" | "failed" | "cancelled" | "interrupted";
export type UsageTokens = { known_tokens: number; complete: boolean; prompt_tokens: number | null; completion_tokens: number | null; total_tokens: number | null; batches: number | null };
export type UsageEvent = {
  id: string; request_id: string; operation: UsageOperation; status: UsageStatus; quota_charged: boolean;
  started_at: string; finished_at: string | null; durations_ms: Record<string, number | null>;
  models: Record<string, string>; attempts: Record<string, number>; token_usage: Record<string, UsageTokens>;
  error_code: string | null;
};
export type UsageEventList = { items: UsageEvent[]; total: number; limit: number; offset: number };
export type UsageSummary = {
  today: string; reset_at: string; recording_started_at: string | null;
  quota: Record<UsageOperation, { limit: number; used: number; remaining: number }>;
  recent: {
    total: number; ended: number; running: number; completed: number; local_completed: number; failed: number;
    cancelled: number; interrupted: number; success_rate: number | null; avg_duration_ms: number | null;
    sample_count: number; known_tokens: number; unknown_usage_count: number;
  };
};
