/**
 * App configuration. The API base URL is read from EXPO_PUBLIC_API_URL (Expo inlines
 * EXPO_PUBLIC_* at build time). On a physical device, point this at your machine's LAN IP,
 * not localhost. Defaults to the local backend.
 */
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';
