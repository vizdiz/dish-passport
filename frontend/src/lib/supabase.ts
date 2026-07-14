// URL polyfill must be installed before supabase-js constructs any request URLs in RN.
import 'react-native-url-polyfill/auto';

import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  // Fail loud in dev; a missing URL/key means auth silently never works otherwise.
  // eslint-disable-next-line no-console
  console.warn(
    'Supabase env missing: set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY.',
  );
}

/**
 * SecureStore-backed storage adapter for the Supabase auth session.
 *
 * SecureStore rejects keys containing characters outside [A-Za-z0-9._-], and Supabase uses keys
 * like `sb-<ref>-auth-token`, so we sanitize the key. SecureStore also caps values at ~2KB on
 * some platforms; a Supabase session (access + refresh JWTs) can exceed that, so we chunk large
 * values across multiple entries and stitch them back together on read.
 */
const CHUNK_SIZE = 1800; // stay comfortably under the ~2KB SecureStore per-value limit

function safeKey(key: string): string {
  return key.replace(/[^A-Za-z0-9._-]/g, '_');
}

const SecureStoreAdapter = {
  getItem: async (key: string): Promise<string | null> => {
    const base = safeKey(key);
    const head = await SecureStore.getItemAsync(base);
    if (head === null) return null;
    // A chunked value is stored as a JSON header describing how many parts to reassemble.
    if (head.startsWith('__chunks__:')) {
      const count = Number(head.slice('__chunks__:'.length));
      let out = '';
      for (let i = 0; i < count; i += 1) {
        const part = await SecureStore.getItemAsync(`${base}.${i}`);
        if (part === null) return null; // corrupt/partial write — treat as no session
        out += part;
      }
      return out;
    }
    return head;
  },
  setItem: async (key: string, value: string): Promise<void> => {
    const base = safeKey(key);
    if (value.length <= CHUNK_SIZE) {
      await SecureStore.setItemAsync(base, value);
      return;
    }
    const count = Math.ceil(value.length / CHUNK_SIZE);
    for (let i = 0; i < count; i += 1) {
      await SecureStore.setItemAsync(
        `${base}.${i}`,
        value.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE),
      );
    }
    await SecureStore.setItemAsync(base, `__chunks__:${count}`);
  },
  removeItem: async (key: string): Promise<void> => {
    const base = safeKey(key);
    const head = await SecureStore.getItemAsync(base);
    if (head?.startsWith('__chunks__:')) {
      const count = Number(head.slice('__chunks__:'.length));
      for (let i = 0; i < count; i += 1) {
        await SecureStore.deleteItemAsync(`${base}.${i}`).catch(() => undefined);
      }
    }
    await SecureStore.deleteItemAsync(base).catch(() => undefined);
  },
};

export const supabase: SupabaseClient = createClient(
  supabaseUrl ?? '',
  supabaseAnonKey ?? '',
  {
    auth: {
      storage: SecureStoreAdapter,
      autoRefreshToken: true,
      persistSession: true,
      // No URL-based session detection in a native app (no browser redirect to parse).
      detectSessionInUrl: false,
    },
  },
);

/**
 * Map the username UX onto Supabase email/password auth. Usernames are lowercased and mapped to a
 * synthetic email so the rest of the auth stack (and the DB trigger that creates the profile from
 * user_metadata.username) can stay email-based. NOTE: use a bare domain — GoTrue's email
 * validator rejects multi-level subdomains like `users.dishport.app`.
 */
export function usernameToEmail(username: string): string {
  return `${username.toLowerCase()}@dishport.app`;
}
