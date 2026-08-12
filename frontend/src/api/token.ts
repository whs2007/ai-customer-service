/**
 * 令牌存取（localStorage）。
 * 独立于 zustand store，供 axios 拦截器直接读取，避免循环依赖。
 */

const ACCESS_TOKEN_KEY = 'ai_cs_access_token';
const REFRESH_TOKEN_KEY = 'ai_cs_refresh_token';

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

