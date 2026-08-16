/** 用户端认证状态（11 §3.4）：独立于管理端 auth store，token 走用户专用 key。 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { CurrentUser } from '../api/auth';
import { registerUser, userLogin, userMe, type RegisterPayload } from '../api/user';
import { clearUserTokens, setUserTokens } from '../api/token';

interface UserAuthState {
  user: CurrentUser | null;
  login: (username: string, password: string) => Promise<CurrentUser>;
  register: (payload: RegisterPayload) => Promise<CurrentUser>;
  loadMe: () => Promise<void>;
  logout: () => void;
}

export const useUserAuthStore = create<UserAuthState>()(
  persist(
    (set) => ({
      user: null,

      login: async (username, password) => {
        const result = await userLogin(username, password);
        setUserTokens(result.access_token, result.refresh_token);
        set({ user: result.user });
        return result.user;
      },

      register: async (payload) => {
        const result = await registerUser(payload);
        setUserTokens(result.access_token, result.refresh_token);
        set({ user: result.user });
        return result.user;
      },

      loadMe: async () => {
        const user = await userMe();
        set({ user });
      },

      logout: () => {
        clearUserTokens();
        set({ user: null });
      },
    }),
    {
      name: 'ai-customer-service-user-auth',
      partialize: (state) => ({ user: state.user }),
    },
  ),
);
