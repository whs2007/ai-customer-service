/** 知识库模块接口（B2：KB / 文档 / Chunk）。 */

import { client, request } from './client';

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  doc_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeBaseDetail {
  id: string;
  name: string;
  description: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentItem {
  id: string;
  kb_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  status: 'uploading' | 'parsing' | 'embedding' | 'completed' | 'failed';
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChunkItem {
  id: string;
  doc_id: string;
  kb_id: string;
  chunk_index: number;
  question: string;
  answer: string;
  category: string | null;
  page: string | null;
  row: string | null;
  word_count: number;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ChunkPayload {
  doc_id?: string;
  question: string;
  answer: string;
  category?: string | null;
  tags?: string[];
  page?: string | null;
  row?: string | null;
}

// ---------- 知识库 ----------

export function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  return request<KnowledgeBase[]>({ url: '/knowledge-bases', method: 'GET' });
}

export function getKnowledgeBase(id: string): Promise<KnowledgeBaseDetail> {
  return request<KnowledgeBaseDetail>({ url: `/knowledge-bases/${id}`, method: 'GET' });
}

export function createKnowledgeBase(data: {
  name: string;
  description: string;
}): Promise<KnowledgeBase> {
  return request<KnowledgeBase>({
    url: '/knowledge-bases',
    method: 'POST',
    data,
  });
}

export function updateKnowledgeBase(
  id: string,
  data: { name: string; description: string },
): Promise<KnowledgeBase> {
  return request<KnowledgeBase>({
    url: `/knowledge-bases/${id}`,
    method: 'PUT',
    data,
  });
}

export function deleteKnowledgeBase(id: string): Promise<null> {
  return request<null>({ url: `/knowledge-bases/${id}`, method: 'DELETE' });
}

// ---------- 文档 ----------

export function listDocuments(
  kbId: string,
  params: { keyword?: string; page: number; page_size: number },
): Promise<PageResult<DocumentItem>> {
  return request<PageResult<DocumentItem>>({
    url: `/knowledge-bases/${kbId}/documents`,
    method: 'GET',
    params,
  });
}

export function getDocument(docId: string): Promise<DocumentItem> {
  return request<DocumentItem>({ url: `/documents/${docId}`, method: 'GET' });
}

export function deleteDocument(docId: string): Promise<null> {
  return request<null>({ url: `/documents/${docId}`, method: 'DELETE' });
}

export function reparseDocument(docId: string): Promise<DocumentItem> {
  return request<DocumentItem>({ url: `/documents/${docId}/reparse`, method: 'POST' });
}

export async function uploadDocument(
  kbId: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<{ document_id: string; file_name: string; status: string }> {
  const form = new FormData();
  form.append('file', file);
  const resp = await client.post(`/knowledge-bases/${kbId}/documents`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (e.total) {
        onProgress?.(Math.round((e.loaded / e.total) * 100));
      }
    },
  });
  return resp.data.data;
}

// ---------- Chunk ----------

export function listChunks(
  docId: string,
  params: { page: number; page_size: number },
): Promise<PageResult<ChunkItem>> {
  return request<PageResult<ChunkItem>>({
    url: `/documents/${docId}/chunks`,
    method: 'GET',
    params,
  });
}

export function createChunk(payload: ChunkPayload): Promise<ChunkItem> {
  return request<ChunkItem>({ url: '/chunks', method: 'POST', data: payload });
}

export function updateChunk(id: string, payload: Partial<ChunkPayload>): Promise<ChunkItem> {
  return request<ChunkItem>({ url: `/chunks/${id}`, method: 'PUT', data: payload });
}

export function deleteChunk(id: string): Promise<null> {
  return request<null>({ url: `/chunks/${id}`, method: 'DELETE' });
}

