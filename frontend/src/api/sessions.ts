/** 会话记录接口（B5）。 */

import { request } from './client';
import type { ChatMessage } from './chat';

export interface SessionListItem {
  id: string;
  status: 'active' | 'closed' | 'transferred';
  channel: string;
  kb_ids: string[];
  escalation_count: number;
  created_at: string;
  updated_at: string;
  message_count: number;
  intent: string | null;
  transferred: boolean;
  ticket_no: string | null;
  annotated: boolean;
}

export interface TraceStep {
  step: string;
  latency_ms: number;
  detail?: Record<string, unknown> | null;
}

export interface Trace {
  request_id: string;
  steps: TraceStep[];
  latency_ms: number;
  created_at: string;
}

export interface TicketBrief {
  id: string;
  ticket_no: string;
  status: string;
  priority: string;
  created_at: string;
}

export interface Annotation {
  id: string;
  session_id: string;
  tags: string[];
  note: string;
  include_in_eval: boolean;
  eval_set_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionDetail {
  session: SessionListItem;
  messages: ChatMessage[];
  trace: Trace | null;
  ticket: TicketBrief | null;
  annotation: Annotation | null;
}

export function listSessions(params: {
  start_date?: string;
  end_date?: string;
  intent?: string;
  status?: string;
  transferred?: boolean;
  keyword?: string;
  annotated?: boolean;
  page: number;
  page_size: number;
}): Promise<{ items: SessionListItem[]; total: number; page: number; page_size: number }> {
  return request({ url: '/sessions', method: 'GET', params });
}

export function getSession(id: string): Promise<SessionDetail> {
  return request({ url: `/sessions/${id}`, method: 'GET' });
}

export function annotateSession(
  id: string,
  payload: { tags: string[]; note: string; include_in_eval: boolean; eval_set_id?: string | null },
): Promise<Annotation> {
  return request({ url: `/sessions/${id}/annotations`, method: 'POST', data: payload });
}

export const INTENT_LABELS: Record<string, string> = {
  order_query: '查询问题',
  policy_query: '知识库问答',
  complaint: '投诉转人工',
  transfer: '转人工',
  other: '普通问题',
};

