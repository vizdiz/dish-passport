import type { Session } from '@supabase/supabase-js';
import { create } from 'zustand';

import { setAuthToken, setUnauthorizedHandler } from '../api/client';
import { supabase, usernameToEmail } from '../lib/supabase';

interface SessionState {
  token: string | null;
  userId: string | null; // Supabase user UUID (was a numeric id under the old worker auth)
  ready: boolean; // hydration finished
  authenticated: boolean;
  hydrate: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

/**
 * The auth seam. Supabase owns the session (persisted in SecureStore via the client's storage
 * adapter and auto-refreshed). We mirror the current Supabase session into this store and feed the
 * access token to the worker API client. A 401 from any worker request triggers logout, dropping
 * the app back to the Auth screen.
 */
export const useSession = create<SessionState>((set, get) => {
  // Push a Supabase session (or lack thereof) into the store and the API client in one place, so
  // hydrate(), login/register, onAuthStateChange (token refresh, cross-tab), and logout all agree.
  const applySession = (session: Session | null) => {
    if (session) {
      setAuthToken(session.access_token);
      set({ token: session.access_token, userId: session.user.id, authenticated: true });
    } else {
      setAuthToken(null);
      set({ token: null, userId: null, authenticated: false });
    }
  };

  return {
    token: null,
    userId: null,
    ready: false,
    authenticated: false,

    hydrate: async () => {
      setUnauthorizedHandler(() => {
        void get().logout();
      });
      // Keep token/authenticated in sync with refreshes and sign-in/out that happen elsewhere.
      supabase.auth.onAuthStateChange((_event, session) => {
        applySession(session);
      });
      try {
        const { data } = await supabase.auth.getSession();
        applySession(data.session);
      } catch {
        // never block startup on storage/network
      }
      set({ ready: true });
    },

    login: async (username, password) => {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: usernameToEmail(username),
        password,
      });
      if (error) throw error;
      applySession(data.session);
    },

    register: async (username, password) => {
      const { data, error } = await supabase.auth.signUp({
        email: usernameToEmail(username),
        password,
        // Lands in user_metadata; a DB trigger creates the profile row from this username.
        options: { data: { username } },
      });
      if (error) throw error;
      // With email confirmation disabled, signUp returns an active session; apply it if present.
      applySession(data.session);
    },

    logout: async () => {
      await supabase.auth.signOut().catch(() => undefined);
      applySession(null);
    },
  };
});
