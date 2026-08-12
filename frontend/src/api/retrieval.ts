/** 检索测试接口（B3）。 */

import { request } from './client';

export type RetrieverMode = 'vector' | 'hybrid' | 'hybrid_rerank';

export interface RetrievalHit {
  chunk_id: string;
  kb_id: string;
  document_name: string;
  page: string | null;
  row: string | null;
  question: string;
  answer: string;
  retrieval_score: number;
  rerank_score: number | null;
}

export interface RetrievalResponse {
  query: string;
  top_k: number;
  retriever_mode: RetrieverMode;
  actual_mode: RetrieverMode;
  rerank_skipped: boolean;
  hits: RetrievalHit[];
}

export interface RetrievalPayload {
  kb_ids: string[];
  query: string;
  top_k: number;
  tags?: string[];
  retriever_mode: RetrieverMode;
}

export function retrievalTest(payload: RetrievalPayload): Promise<RetrievalResponse> {
  return request<RetrievalResponse>({
    url: '/retrieval/test',
    method: 'POST',
    data: payload,
  });
}

