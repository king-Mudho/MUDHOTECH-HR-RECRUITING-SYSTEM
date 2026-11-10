import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

type S = components["schemas"];
export type UploadedDocument = S["Document"];
export type UploadPurpose = S["UploadSessionCreateRequest"]["purpose"];
export type UploadSession = S["UploadSession"];

export const documentsApi = {
  createSession: (body: { purpose: UploadPurpose; filename: string; mime: string; size: number }) =>
    api.post<UploadSession>("/documents/upload-sessions/", body),
  complete: (sessionId: string) =>
    api.post<UploadedDocument>(`/documents/upload-sessions/${sessionId}/complete/`),
  directUpload: (purpose: UploadPurpose, file: File) => {
    const form = new FormData();
    form.append("purpose", purpose);
    form.append("file", file);
    return api.post<UploadedDocument>("/documents/direct-upload/", form);
  },
  get: (id: string) => api.get<UploadedDocument>(`/documents/${id}/`),
  downloadUrl: (id: string) => `/api/v1/documents/${id}/download/`,
};

/**
 * PUT a file straight to storage with progress (presigned URL). Rejects with an ApiError
 * (status 0 for network/CORS failures) so callers can fall back to the direct upload.
 */
export function putWithProgress(
  url: string,
  file: File,
  headers: Record<string, string>,
  onProgress: (fraction: number) => void,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new ApiError(xhr.status, "upload_failed", "The upload failed."));
    xhr.onerror = () => reject(new ApiError(0, "network_error", "The upload was interrupted."));
    xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
    signal.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(file);
  });
}
