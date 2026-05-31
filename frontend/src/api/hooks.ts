import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './client';
import type { LogRequest } from './types';

export const qk = {
  dish: (id: number) => ['dish', id] as const,
  similar: (id: number, n: number) => ['similar', id, n] as const,
  recommendations: (userId: number, n: number) => ['recommendations', userId, n] as const,
  taste: (userId: number) => ['taste', userId] as const,
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

export function useRecommendations(userId: number, n = 10) {
  return useQuery({
    queryKey: qk.recommendations(userId, n),
    queryFn: () => api.getRecommendations(userId, n),
  });
}

export function useTasteProfile(userId: number) {
  return useQuery({
    queryKey: qk.taste(userId),
    queryFn: () => api.getTasteProfile(userId),
    retry: false, // 404 until rebuild_taste_profiles has run for this user
  });
}

export function useLogDish(userId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Omit<LogRequest, 'user_id'>) => api.createLog({ ...body, user_id: userId }),
    onSuccess: () => {
      // a new log shifts both the feed and the taste profile inputs
      void qc.invalidateQueries({ queryKey: ['recommendations'] });
      void qc.invalidateQueries({ queryKey: qk.taste(userId) });
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
