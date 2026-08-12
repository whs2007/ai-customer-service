/**
 * axios 封装：统一响应解包（08 §6.1 {code, message, data}）、
 * Bearer 注入、40100/40101 自动刷新与跳转登录。
 */

import axios, { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios';

import { getAccessToken, getRefreshToken, setTokens, clearTokens } from './token';

export interface ApiResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

export class ApiError extends Error {
  code: number;

  constructor(code: number, message: string) {
    super(message);
    this.code = code;
  }
}

export const client = axios.create({
  baseURL: '/api',
  timeout: 20000,
});

client.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  try {
    const resp = await axios.post<ApiResponse<{ access_token: string; refresh_token: string }>>(
      '/api/auth/refresh',
      { refresh_token: refreshToken },
    );
    if (resp.data.code === 0) {
      setTokens(resp.data.data.access_token, resp.data.data.refresh_token);
      return resp.data.data.access_token;
    }
  } catch {
    // 刷新失败走登出
  }
  return null;
}

client.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse | undefined;
    if (body && typeof body.code === 'number' && body.code !== 0) {
      return Promise.reject(new ApiError(body.code, body.message || '请求失败'));
    }
    return response;
  },
  async (error: AxiosError) => {
    const body = error.response?.data as ApiResponse | undefined;
    const code = body?.code ?? 50000;
    const message = body?.message || '请求失败，请稍后重试';

    // access 过期：尝试用 refresh 换新（40101）
    if (code === 40101) {
      refreshing = refreshing ?? refreshAccessToken().finally(() => {
        refreshing = null;
      });
      const token = await refreshing;
      if (token && error.config) {
        const config: InternalAxiosRequestConfig = { ...error.config };
        config.headers = AxiosHeaders.from(error.config.headers ?? {});
        config.headers.set('Authorization', `Bearer ${token}`);
        return client.request(config);
      }
    }

    // 未登录 / 刷新失败：清空并跳转登录页
    if (code === 40100 || code === 40101) {
      clearTokens();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(new ApiError(code, message));
  },
);

/** 请求辅助：解包统一响应 data */
export async function request<T>(config: Parameters<typeof client.request>[0]): Promise<T> {
  const resp = await client.request<ApiResponse<T>>(config);
  return resp.data.data;
}
