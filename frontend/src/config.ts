/**
 * App configuration. All values are read from EXPO_PUBLIC_* env vars (Expo inlines these at build
 * time). On a physical device, point API_URL at your machine's LAN IP, not localhost.
 *
 * Auth is owned by Supabase (see src/lib/supabase.ts) and reads:
 *   - EXPO_PUBLIC_SUPABASE_URL       the Supabase project URL
 *   - EXPO_PUBLIC_SUPABASE_ANON_KEY  the Supabase anon/public key
 *
 * API_URL below is the Python worker API used for all data/compute (logs, recommendations,
 * similar, taste-profile, dish reads). Worker requests are authenticated with the Supabase
 * session access token as a Bearer token.
 */
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';
