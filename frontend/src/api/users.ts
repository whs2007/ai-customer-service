/** 用户管理接口（B6a）。 */

import { request } from './client';

export interface AdminUser {
  id: string;
  username: string;
  display_name: string;
  role: 'admin' | 'agent' | 'viewer';
  status: 'active' | 'disabled';
  last_login_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export function listUsers(params: { page: number; page_size: number }): Promise<{
  items: AdminUser[];
  total: number;
  page: number;
  page_size: number;
}> {
  return request({ url: '/auth/users', method: 'GET', params });
}

export function createUser(data: {
  username: string;
  password: string;
  display_name: string;
  role: string;
  status: string;
}): Promise<AdminUser> {
  return request({ url: '/auth/users', method: 'POST', data });
}

export function updateUser(
  id: string,
  data: { display_name?: string; role?: string; status?: string },
): Promise<AdminUser> {
  return request({ url: `/auth/users/${id}`, method: 'PUT', data });
}

export function resetUserPassword(id: string, password: string): Promise<null> {
  return request({ url: `/auth/users/${id}/password`, method: 'PUT', data: { password } });
}

