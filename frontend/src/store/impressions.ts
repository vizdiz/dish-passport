import { create } from 'zustand';

import { api } from '../api/client';
import type { ImpressionEvent } from '../api/types';

const DEBOUNCE_MS = 1500;
let timer: ReturnType<typeof setTimeout> | null = null;

interface ImpressionState {
  /** Pending events, keyed by dish_id (latest wins) so a card seen twice counts once per flush. */
  buffer: Record<number, ImpressionEvent>;
  /** Record a card becoming viewable; schedules a debounced flush. */
  track: (event: ImpressionEvent) => void;
  /** Send buffered events now (call on scroll-settle / screen blur). Best-effort. */
  flush: () => Promise<void>;
}

/**
 * Soft-negative pipe. The feed calls `track` when a rec card crosses the viewability
 * threshold; events are batched + debounced and flushed on scroll-settle. The backend turns
 * non-converted impressions into decaying soft negatives in rebuild_taste_profiles.
 */
export const useImpressions = create<ImpressionState>((set, get) => ({
  buffer: {},
  track: (event) => {
    set((s) => ({ buffer: { ...s.buffer, [event.dish_id]: event } }));
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      void get().flush();
    }, DEBOUNCE_MS);
  },
  flush: async () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    const events = Object.values(get().buffer);
    if (events.length === 0) return;
    set({ buffer: {} });
    try {
      await api.postImpressions(events);
    } catch {
      // best-effort telemetry; drop on failure rather than retrying forever
    }
  },
}));
