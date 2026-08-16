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
  role: 'admin' | 'agent' | 'viewer' | 'user';
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

/** 用指定 token 拉取当前用户（统一登录页按角色分流用）。 */
export function meByToken(token: string): Promise<CurrentUser> {
  return request<CurrentUser>({
    url: '/auth/me',
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}
