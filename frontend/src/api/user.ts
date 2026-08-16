/** 用户端接口（12 / 开发文档 01 §3）：注册登录、会话、工单、评价、SSE 对话。 */

import { userRequest } from './userClient';
import { getUserAccessToken } from './token';
import type { CurrentUser } from './auth';

export interface UserSessionItem {
  id: string;
  status: 'active' | 'closed' | 'transferred';
  updated_at: string;
  message_count: number;
  last_message: string;
  ticket_no: string | null;
}

export interface UserMessage {
  id: string;
  role: 'user' | 'assistant' | 'agent' | 'system';
  content: string;
  created_at: string;
}

export interface UserSessionDetail {
  session: {
    id: string;
    status: string;
    channel: string;
    created_at: string;
    updated_at: string;
  };
  messages: UserMessage[];
}

export interface UserTicket {
  id: string;
  ticket_no: string;
  status: 'open' | 'processing' | 'closed';
  priority: 'high' | 'medium' | 'low';
  session_id: string;
  claimed_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserTicketDetail {
  ticket: UserTicket;
  messages: UserMessage[];
  rating: { score: number; comment: string | null } | null;
  can_rate: boolean;
}

export interface RegisterPayload {
  username: string;
  password: string;
  confirm_password: string;
  display_name?: string;
  captcha_id: string;
  captcha: string;
}

export interface RegisterResult {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: CurrentUser;
}

export function getCaptcha(): Promise<{ captcha_id: string; question: string }> {
  return userRequest({ url: '/auth/captcha', method: 'POST' });
}

export function registerUser(payload: RegisterPayload): Promise<RegisterResult> {
  return userRequest({ url: '/auth/register', method: 'POST', data: payload });
}

export function userLogin(username: string, password: string): Promise<RegisterResult> {
  return userRequest({
    url: '/auth/login',
    method: 'POST',
    data: { username, password },
  });
}

export function userMe(): Promise<CurrentUser> {
  return userRequest({ url: '/auth/me', method: 'GET' });
}

export function changePassword(
  old_password: string,
  new_password: string,
): Promise<null> {
  return userRequest({
    url: '/auth/password',
    method: 'PUT',
    data: { old_password, new_password },
  });
}

export function listUserSessions(params: {
  page?: number;
  page_size?: number;
}): Promise<{ items: UserSessionItem[]; total: number; page: number; page_size: number }> {
  return userRequest({ url: '/user/sessions', method: 'GET', params });
}

export function getUserSession(id: string): Promise<UserSessionDetail> {
  return userRequest({ url: `/user/sessions/${id}`, method: 'GET' });
}

export function markUserSessionRead(
  id: string,
  last_read_message_id?: string | null,
): Promise<{ ok: boolean }> {
  return userRequest({
    url: `/user/sessions/${id}/read`,
    method: 'POST',
    data: { last_read_message_id: last_read_message_id ?? null },
  });
}

export function listUserTickets(params: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<{ items: UserTicket[]; total: number; page: number; page_size: number }> {
  return userRequest({ url: '/user/tickets', method: 'GET', params });
}

export function getUserTicket(id: string): Promise<UserTicketDetail> {
  return userRequest({ url: `/user/tickets/${id}`, method: 'GET' });
}

export function rateUserTicket(
  id: string,
  data: { score: number; comment?: string },
): Promise<{ id: string; score: number; comment: string | null }> {
  return userRequest({ url: `/user/tickets/${id}/rating`, method: 'POST', data });
}

export type UserChatEvent =
  | { event: 'message_start'; data: { session_id: string } }
  | { event: 'token'; data: { content: string } }
  | { event: 'form'; data: unknown }
  | { event: 'citations'; data: { citations: { document_name: string; question: string }[] } }
  | {
      event: 'done';
      data: {
        message_id: string | null;
        intent: string | null;
        ticket_no: string | null;
        session_id: string;
      };
    }
  | { event: 'error'; data: { code: string; message: string } };

/** 用户端 SSE 流式对话（带 Authorization 头，可 AbortSignal 停止）。 */
export async function userChatStream(
  payload: { session_id?: string | null; message: string },
  onEvent: (event: UserChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const resp = await fetch('/api/user/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getUserAccessToken() ?? ''}`,
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
            onEvent({ event: eventName, data: JSON.parse(line.slice(5).trim()) } as UserChatEvent);
          } catch {
            // 忽略无法解析的数据行
          }
        }
      }
    }
  }
}
