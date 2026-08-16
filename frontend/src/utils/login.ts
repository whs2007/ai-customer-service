/**
 * 统一登录：账号密码登录后按角色写入对应端 token 并跳转（11 §3.4 隔离要求）。
 * user → 用户端 key + /user/chat；agent/admin → 管理端 key + /workbench|/dashboard。
 */

import { loginRequest, meByToken } from '../api/auth';
import { setTokens, setUserTokens } from '../api/token';
import { useAuthStore } from '../stores/auth';
import { useUserAuthStore } from '../stores/userAuth';
import { redirectByRole } from './redirect';

export async function loginAndRoute(
  username: string,
  password: string,
  navigate: (path: string, opts?: { replace?: boolean }) => void,
): Promise<string> {
  const tokens = await loginRequest(username, password);
  const me = await meByToken(tokens.access_token);
  if (me.role === 'user') {
    setUserTokens(tokens.access_token, tokens.refresh_token);
    useUserAuthStore.setState({ user: me });
  } else {
    setTokens(tokens.access_token, tokens.refresh_token);
    useAuthStore.setState({
      user: me,
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    });
  }
  const target = redirectByRole(me.role);
  navigate(target, { replace: true });
  return target;
}
