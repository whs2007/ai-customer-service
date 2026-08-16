/**
 * 用户端 axios 实例（11 §3.4）：使用独立 localStorage key，
 * 与管理端/客服端 token 完全隔离；统一响应解包与 401 刷新逻辑。
 */

import axios, { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios';

import { ApiError, type ApiResponse } from './client';
import {
  clearUserTokens,
  getUserAccessToken,
  getUserRefreshToken,
  setUserTokens,
} from './token';

export const userClient = axios.create({
  baseURL: '/api',
  timeout: 20000,
});

userClient.interceptors.request.use((config) => {
  const token = getUserAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function refreshUserAccessToken(): Promise<string | null> {
  const refreshToken = getUserRefreshToken();
  if (!refreshToken) return null;
  try {
    const resp = await axios.post<ApiResponse<{ access_token: string; refresh_token: string }>>(
      '/api/auth/refresh',
      { refresh_token: refreshToken },
    );
    if (resp.data.code === 0) {
      setUserTokens(resp.data.data.access_token, resp.data.data.refresh_token);
      return resp.data.data.access_token;
    }
  } catch {
    // 刷新失败走登出
  }
  return null;
}

userClient.interceptors.response.use(
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

    if (code === 40101) {
      refreshing = refreshing ?? refreshUserAccessToken().finally(() => {
        refreshing = null;
      });
      const token = await refreshing;
      if (token && error.config) {
        const config: InternalAxiosRequestConfig = { ...error.config };
        config.headers = AxiosHeaders.from(error.config.headers ?? {});
        config.headers.set('Authorization', `Bearer ${token}`);
        return userClient.request(config);
      }
    }

    if (code === 40100 || code === 40101) {
      clearUserTokens();
      if (!window.location.pathname.startsWith('/user/')) {
        window.location.href = '/user/login';
      }
    }
    return Promise.reject(new ApiError(code, message));
  },
);

/** 请求辅助：解包统一响应 data */
export async function userRequest<T>(
  config: Parameters<typeof userClient.request>[0],
): Promise<T> {
  const resp = await userClient.request<ApiResponse<T>>(config);
  return resp.data.data;
}
