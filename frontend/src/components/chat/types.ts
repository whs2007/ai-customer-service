/** 聊天展示层通用类型（用户端/工作台共用）。 */

export interface DisplayCitation {
  document_name: string;
  question?: string;
  answer?: string;
  page?: string | null;
  row?: string | null;
  retrieval_score?: number | null;
  rerank_score?: number | null;
}

export interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant' | 'agent' | 'system';
  content: string;
  created_at: string;
  citations?: DisplayCitation[];
}
