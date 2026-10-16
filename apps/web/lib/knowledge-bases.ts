export type KnowledgeBase = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type KnowledgeBaseList = {
  items: KnowledgeBase[];
  total: number;
  limit: number;
  offset: number;
};
