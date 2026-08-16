/** token 存取（localStorage）单元测试。 */

import { afterEach, describe, expect, it } from 'vitest';

import { clearTokens, getAccessToken, getRefreshToken, setTokens } from './token';

afterEach(() => {
  localStorage.clear();
});

describe('token storage', () => {
  it('setTokens 写入 access/refresh，getTokens 可读回', () => {
    setTokens('access-1', 'refresh-1');
    expect(getAccessToken()).toBe('access-1');
    expect(getRefreshToken()).toBe('refresh-1');
  });

  it('clearTokens 清空两类令牌', () => {
    setTokens('access-1', 'refresh-1');
    clearTokens();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});
