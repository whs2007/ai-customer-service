/** 客服工作台接口（13 / 开发文档 01 §5）：队列、认领、回复、关闭、在线、已读。 */

import { request } from './client';

export interface AgentTicketItem {
  id: string;
  ticket_no: string;
  status: 'open' | 'processing' | 'closed';
  priority: 'high' | 'medium' | 'low';
  user_id: string | null;
  user_name: string;
  session_id: string;
  unread_count: number;
  last_message: string;
  last_message_at: string | null;
  claimed_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentCitation {
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

export interface AgentMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'agent' | 'system';
  content: string;
  intent: string | null;
  cited_chunk_ids: string[];
  citations?: AgentCitation[];
  created_at: string;
}

export interface AgentTicketDetail {
  ticket: {
    id: string;
    ticket_no: string;
    session_id: string;
    type: string;
    content: string;
    status: string;
    priority: string;
    assignee_id: string | null;
    claimed_at: string | null;
    closed_at: string | null;
    close_reason: string | null;
    created_at: string;
    updated_at: string;
  };
  user: { id: string; username: string; display_name: string } | null;
  messages: AgentMessage[];
  rating: { score: number; comment: string | null } | null;
  unread_count: number;
  notes: {
    id: string;
    note: string;
    status_from: string | null;
    status_to: string | null;
    operator: string;
    created_at: string;
  }[];
}

export interface TicketsOverview {
  total: number;
  open: number;
  processing: number;
  closed_today: number;
  stale_open: { ticket_no: string; created_at: string; minutes: number }[];
}

export function listAgentTickets(params: {
  status?: string;
  mine?: boolean;
  page?: number;
  page_size?: number;
}): Promise<{ items: AgentTicketItem[]; total: number; page: number; page_size: number }> {
  return request({ url: '/agent/tickets', method: 'GET', params });
}

export function claimTicket(id: string): Promise<{ id: string; ticket_no: string; status: string }> {
  return request({ url: `/agent/tickets/${id}/claim`, method: 'POST' });
}

export function getAgentTicket(id: string): Promise<AgentTicketDetail> {
  return request({ url: `/agent/tickets/${id}`, method: 'GET' });
}

export function replyTicket(id: string, content: string): Promise<AgentMessage> {
  return request({ url: `/agent/tickets/${id}/reply`, method: 'POST', data: { content } });
}

export function closeTicket(id: string, reason: string): Promise<{ status: string }> {
  return request({ url: `/agent/tickets/${id}/close`, method: 'POST', data: { reason } });
}

export function releaseTicket(
  id: string,
  reason?: string,
): Promise<{ id: string; ticket_no: string; status: string }> {
  return request({
    url: `/agent/tickets/${id}/release`,
    method: 'POST',
    data: { reason: reason ?? '' },
  });
}

export function setAgentStatus(online: boolean): Promise<{ online: boolean }> {
  return request({ url: '/agent/status', method: 'PUT', data: { online } });
}

export function getAgentStatus(): Promise<{ online: boolean }> {
  return request({ url: '/agent/status', method: 'GET' });
}

export function markAgentSessionRead(
  sessionId: string,
  last_read_message_id?: string | null,
): Promise<{ ok: boolean }> {
  return request({
    url: `/agent/sessions/${sessionId}/read`,
    method: 'POST',
    data: { last_read_message_id: last_read_message_id ?? null },
  });
}

export function getTicketsOverview(): Promise<TicketsOverview> {
  return request({ url: '/admin/tickets/overview', method: 'GET' });
}

export interface ChannelConfig {
  channel: string;
  default_kb_ids: string[];
  allow_human: boolean;
  business_hours: Record<string, unknown> | null;
  updated_at?: string;
}

export function getChannelConfig(): Promise<ChannelConfig> {
  return request({ url: '/settings/channel', method: 'GET' });
}

export function updateChannelConfig(
  data: Omit<ChannelConfig, 'updated_at'>,
): Promise<ChannelConfig> {
  return request({ url: '/settings/channel', method: 'PUT', data });
}
