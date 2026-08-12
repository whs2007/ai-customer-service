/** 智能客服接口（B4）：SSE 流式对话、会话恢复、引用反馈、模型配置。 */

import { getAccessToken } from './token';
import { request } from './client';

export interface ChatSession {
  id: string;
  status: 'active' | 'closed' | 'transferred';
  channel: string;
  kb_ids: string[];
  escalation_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  intent: string | null;
  cited_chunk_ids: string[];
  citations?: Citation[];
  created_at: string;
}

export interface Citation {
  chunk_id: string;
  kb_id: string;
  document_name: string;
  page: string | null;
  row: string | null;
  question: string;
  answer: string;
  retrieval_score: number | null;
  rerank_score: number | null;
}

export interface ChatFormField {
  name: string;
  label: string;
  type: 'text';
  required: boolean;
  pattern: string;
  message: string;
}

export interface ChatForm {
  fields: ChatFormField[];
}

export interface ModelProfile {
  id: string;
  name: string;
  provider: string;
  model: string;
  base_url: string | null;
  api_key: string;
  temperature: number;
  top_p: number;
  max_tokens: number;
  role: string;
  is_default: boolean;
  enabled: boolean;
}

export type ChatEvent =
  | { event: 'message_start'; data: { session_id: string } }
  | { event: 'token'; data: { content: string } }
  | { event: 'form'; data: ChatForm }
  | { event: 'citations'; data: { citations: Citation[] } }
  | {
      event: 'done';
      data: { message_id: string | null; intent: string | null; ticket_no: string | null; session_id: string };
    }
  | { event: 'error'; data: { code: string; message: string } };

export interface ChatPayload {
  session_id?: string | null;
  kb_ids: string[];
  message: string;
  model_profile_id?: string | null;
  form_data?: Record<string, string> | null;
}

/** 发起 SSE 对话：逐事件回调（可被 AbortSignal 停止）。 */
export async function chatStream(
  payload: ChatPayload,
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const resp = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getAccessToken() ?? ''}`,
    },
    body: JSON.stringify(payload),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`对话请求失败（HTTP ${resp.status}）`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let eventName = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const part of parts) {
      for (const line of part.split('\n')) {
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          try {
            onEvent({
              event: eventName,
              data: JSON.parse(line.slice(5).trim()),
            } as ChatEvent);
          } catch {
            // 忽略无法解析的数据行
          }
        }
      }
    }
  }
}

export function listSessions(params?: { page?: number; page_size?: number }): Promise<{
  items: ChatSession[];
  total: number;
  page: number;
  page_size: number;
}> {
  return request({ url: '/sessions', method: 'GET', params });
}

export function getSession(id: string): Promise<{ session: ChatSession; messages: ChatMessage[] }> {
  return request({ url: `/sessions/${id}`, method: 'GET' });
}

/** 补充引用候选（03 §4.4：从候选片段中选择，08 §6.2 新增）。 */
export function retrievalCandidates(payload: {
  kb_ids: string[];
  query: string;
  top_n?: number;
}): Promise<{ query: string; top_n: number; hits: Citation[] }> {
  return request({ url: '/retrieval/candidates', method: 'POST', data: payload });
}

export function createFeedback(payload: {
  session_id: string;
  message_id: string;
  chunk_id: string;
  action: 'delete' | 'invalid' | 'add';
  reason?: string;
}): Promise<unknown> {
  return request({ url: '/feedbacks', method: 'POST', data: payload });
}

export function listModelProfiles(): Promise<ModelProfile[]> {
  return request({ url: '/settings/model-profiles', method: 'GET' });
}
