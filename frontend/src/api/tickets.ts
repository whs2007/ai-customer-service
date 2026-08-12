/** 客服工单接口（B5）。 */

import { request } from './client';

export interface TicketItem {
  id: string;
  ticket_no: string;
  session_id: string;
  type: string;
  content: string;
  status: 'open' | 'processing' | 'closed';
  priority: 'high' | 'medium' | 'low';
  created_at: string;
  updated_at: string;
}

export interface TicketNote {
  id: string;
  note: string;
  status_from: string | null;
  status_to: string | null;
  operator: string;
  created_at: string;
}

export interface TicketCitation {
  chunk_id: string;
  kb_id: string;
  document_name: string;
  page: string | null;
  row: string | null;
  question: string;
  answer: string;
}

export interface TicketDetail extends TicketItem {
  citations: TicketCitation[];
  notes: TicketNote[];
}

export function listTickets(params: {
  status?: string;
  priority?: string;
  start_date?: string;
  end_date?: string;
  keyword?: string;
  page: number;
  page_size: number;
}): Promise<{ items: TicketItem[]; total: number; page: number; page_size: number }> {
  return request({ url: '/tickets', method: 'GET', params });
}

export function getTicket(id: string): Promise<TicketDetail> {
  return request({ url: `/tickets/${id}`, method: 'GET' });
}

export function ticketAction(
  id: string,
  data: { action: 'start' | 'close'; note: string },
): Promise<{ id: string; ticket_no: string; status: string }> {
  return request({ url: `/tickets/${id}/action`, method: 'POST', data });
}

