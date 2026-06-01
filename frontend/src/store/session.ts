import * as SecureStore from 'expo-secure-store';
import { create } from 'zustand';

import { api, setAuthToken, setUnauthorizedHandler } from '../api/client';

const TOKEN_KEY = 'dishport.token';

interface SessionState {
  token: string | null;
  userId: number | null;
  ready: boolean; // hydration finished
  authenticated: boolean;
  hydrate: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

/**
 * The auth seam. Holds the JWT in SecureStore and feeds it to the API client. A 401 from any
 * request triggers logout, dropping the app back to the Auth screen.
 */
export const useSession = create<SessionState>((set, get) => ({
  token: null,
  userId: null,
  ready: false,
  authenticated: false,

  hydrate: async () => {
    setUnauthorizedHandler(() => {
      void get().logout();
    });
    try {
      const token = await SecureStore.getItemAsync(TOKEN_KEY);
      if (token) {
        setAuthToken(token);
        set({ token, authenticated: true });
      }
    } catch {
      // never block startup on storage
    }
    set({ ready: true });
  },

  login: async (username, password) => {
    const res = await api.login(username, password);
    await SecureStore.setItemAsync(TOKEN_KEY, res.access_token);
    setAuthToken(res.access_token);
    set({ token: res.access_token, userId: res.user_id, authenticated: true });
  },

  register: async (username, password) => {
    const res = await api.register(username, password);
    await SecureStore.setItemAsync(TOKEN_KEY, res.access_token);
    setAuthToken(res.access_token);
    set({ token: res.access_token, userId: res.user_id, authenticated: true });
  },

  logout: async () => {
    await SecureStore.deleteItemAsync(TOKEN_KEY).catch(() => undefined);
    setAuthToken(null);
    set({ token: null, userId: null, authenticated: false });
  },
}));
