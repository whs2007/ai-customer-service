/** 认证接口（B1：login / me / refresh）。 */

import { request } from './client';

export interface LoginResult {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface CurrentUser {
  id: string;
  username: string;
  display_name: string;
  role: 'admin' | 'agent' | 'viewer';
  status: string;
  last_login_at: string | null;
  created_at: string;
}

export function loginRequest(username: string, password: string): Promise<LoginResult> {
  return request<LoginResult>({
    url: '/auth/login',
    method: 'POST',
    data: { username, password },
  });
}

export function meRequest(): Promise<CurrentUser> {
  return request<CurrentUser>({ url: '/auth/me', method: 'GET' });
}

