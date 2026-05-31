import * as SecureStore from 'expo-secure-store';
import { create } from 'zustand';

import { DEV_USER_ID } from '../config';

const KEY = 'dishport.user_id';

interface SessionState {
  userId: number;
  ready: boolean;
  /** Load the user id from secure storage (seeding the dev id on first run). */
  hydrate: () => Promise<void>;
  setUserId: (id: number) => Promise<void>;
}

/**
 * The auth seam. Today it just holds a stubbed `user_id` in SecureStore; real login slots in
 * here later (store the token, derive the id) without touching the rest of the app.
 */
export const useSession = create<SessionState>((set) => ({
  userId: DEV_USER_ID,
  ready: false,
  hydrate: async () => {
    try {
      const stored = await SecureStore.getItemAsync(KEY);
      if (stored) {
        set({ userId: Number(stored), ready: true });
      } else {
        await SecureStore.setItemAsync(KEY, String(DEV_USER_ID));
        set({ ready: true });
      }
    } catch {
      set({ ready: true }); // never block the app on storage
    }
  },
  setUserId: async (id) => {
    await SecureStore.setItemAsync(KEY, String(id));
    set({ userId: id });
  },
}));
