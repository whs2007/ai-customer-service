/**
 * 令牌存取（localStorage）。
 * 独立于 zustand store，供 axios 拦截器直接读取，避免循环依赖。
 */

const ACCESS_TOKEN_KEY = 'ai_cs_access_token';
const REFRESH_TOKEN_KEY = 'ai_cs_refresh_token';
// 用户端独立令牌（11 §3.4）：与管理端/客服端 key 隔离，避免互相覆盖
const USER_ACCESS_TOKEN_KEY = 'ai_cs_user_access_token';
const USER_REFRESH_TOKEN_KEY = 'ai_cs_user_refresh_token';

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function getUserAccessToken(): string | null {
  return localStorage.getItem(USER_ACCESS_TOKEN_KEY);
}

export function getUserRefreshToken(): string | null {
  return localStorage.getItem(USER_REFRESH_TOKEN_KEY);
}

export function setUserTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(USER_ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(USER_REFRESH_TOKEN_KEY, refreshToken);
}

export function clearUserTokens(): void {
  localStorage.removeItem(USER_ACCESS_TOKEN_KEY);
  localStorage.removeItem(USER_REFRESH_TOKEN_KEY);
}
