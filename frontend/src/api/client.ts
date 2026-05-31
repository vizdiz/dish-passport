import * as FileSystem from 'expo-file-system';

import { API_URL } from '../config';
import type {
  Dish,
  ImpressionEvent,
  LogRequest,
  LogResponse,
  RecommendationsResponse,
  SimilarResponse,
  TasteProfile,
} from './types';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

interface PresignResponse {
  upload_url: string;
  public_url: string;
  key: string;
  headers: Record<string, string>; // exact headers to send with the PUT (provider-specific)
}

export const api = {
  getDish: (id: number) => request<Dish>(`/dishes/${id}`),
  getSimilar: (id: number, n = 10) => request<SimilarResponse>(`/dishes/${id}/similar?n=${n}`),
  getRecommendations: (userId: number, n = 10) =>
    request<RecommendationsResponse>(`/recommendations?user_id=${userId}&n=${n}`),
  getTasteProfile: (userId: number) => request<TasteProfile>(`/users/${userId}/taste-profile`),
  createLog: (body: LogRequest) =>
    request<LogResponse>('/logs', { method: 'POST', body: JSON.stringify(body) }),
  refineFlavor: (logId: number, flavor: Record<string, number>) =>
    request<{ log_id: number; flavor_override: Record<string, number> }>(
      `/logs/${logId}/flavor`,
      { method: 'PATCH', body: JSON.stringify({ flavor }) },
    ),
  postImpressions: (events: ImpressionEvent[]) =>
    request<{ ingested: number }>('/impressions', { method: 'POST', body: JSON.stringify(events) }),
  presignUpload: (contentType: string) =>
    request<PresignResponse>('/uploads/presign', {
      method: 'POST',
      body: JSON.stringify({ content_type: contentType }),
    }),
};

/** Presign + PUT a local image straight to S3; returns the public URL to attach to a log. */
export async function uploadPhoto(uri: string, contentType = 'image/jpeg'): Promise<string> {
  const { upload_url, public_url, headers } = await api.presignUpload(contentType);
  const res = await FileSystem.uploadAsync(upload_url, uri, {
    httpMethod: 'PUT',
    uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
    headers: { 'Content-Type': contentType, ...(headers ?? {}) },
  });
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`photo upload failed (HTTP ${res.status})`);
  }
  return public_url;
}
