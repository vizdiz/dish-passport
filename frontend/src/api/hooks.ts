import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './client';
import type { LogRequest } from './types';

export const qk = {
  dish: (id: number) => ['dish', id] as const,
  similar: (id: number, n: number) => ['similar', id, n] as const,
  recommendations: (n: number) => ['recommendations', n] as const,
  taste: () => ['taste'] as const,
};

export function useDish(id: number) {
  return useQuery({
    queryKey: qk.dish(id),
    queryFn: () => api.getDish(id),
    enabled: Number.isFinite(id),
  });
}

export function useSimilar(id: number, n = 10) {
  return useQuery({
    queryKey: qk.similar(id, n),
    queryFn: () => api.getSimilar(id, n),
    enabled: Number.isFinite(id),
  });
}

export function useRecommendations(n = 10) {
  return useQuery({
    queryKey: qk.recommendations(n),
    queryFn: () => api.getRecommendations(n),
  });
}

export function useTasteProfile() {
  return useQuery({
    queryKey: qk.taste(),
    queryFn: () => api.getTasteProfile(),
    retry: false, // 404 until rebuild_taste_profiles has run for this user
  });
}

export function useLogDish() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LogRequest) => api.createLog(body),
    onSuccess: () => {
      // a new log shifts both the feed and the taste profile inputs
      void qc.invalidateQueries({ queryKey: ['recommendations'] });
      void qc.invalidateQueries({ queryKey: qk.taste() });
    },
  });
}

export function useRefineFlavor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ logId, flavor }: { logId: number; flavor: Record<string, number> }) =>
      api.refineFlavor(logId, flavor),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['dish'] });
    },
  });
}
