/** 认证状态（zustand + persist）：用户信息与令牌。 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { loginRequest, meRequest, type CurrentUser } from '../api/auth';
import { clearTokens, setTokens } from '../api/token';

interface AuthState {
  user: CurrentUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  loadMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,

      login: async (username, password) => {
        const tokens = await loginRequest(username, password);
        setTokens(tokens.access_token, tokens.refresh_token);
        const user = await meRequest();
        set({
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          user,
        });
      },

      logout: () => {
        clearTokens();
        set({ user: null, accessToken: null, refreshToken: null });
      },

      loadMe: async () => {
        const user = await meRequest();
        set({ user });
      },
    }),
    {
      name: 'ai-customer-service-auth',
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    },
  ),
);

