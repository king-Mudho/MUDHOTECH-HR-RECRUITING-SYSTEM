/**
 * Same-origin fetch wrapper for the MHRS API (docs/04 §1, ADR-004).
 *
 * - Sends cookies (`credentials: "same-origin"`); never stores tokens in JS storage.
 * - Adds `X-CSRFToken` (from the `csrftoken` cookie) on unsafe methods.
 * - Adds `X-Org-Id` for staff calls when an organisation context is supplied.
 * - Parses the standard error envelope into a typed {@link ApiError} that carries the request id.
 */

export const API_BASE = "/api/v1";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export type ErrorDetails = Record<string, unknown>;

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: ErrorDetails;
    request_id: string | null;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetails;
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: ErrorDetails = {},
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  /** Field-level messages for form mapping (`{ closes_at: ["Must be in the future."] }`). */
  fieldErrors(): Record<string, string[]> {
    const out: Record<string, string[]> = {};
    for (const [field, value] of Object.entries(this.details)) {
      if (Array.isArray(value)) out[field] = value.map(String);
      else if (typeof value === "string") out[field] = [value];
    }
    return out;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

export function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const err = (body as { error: unknown }).error;
  return (
    typeof err === "object" &&
    err !== null &&
    typeof (err as { code?: unknown }).code === "string" &&
    typeof (err as { message?: unknown }).message === "string"
  );
}

/** Read a cookie value in the browser (returns null on the server). */
export function getCookie(name: string, cookieString?: string): string | null {
  const source = cookieString ?? (typeof document !== "undefined" ? document.cookie : "");
  for (const part of source.split(";")) {
    const [rawKey, ...rest] = part.trim().split("=");
    if (rawKey === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions extends Omit<RequestInit, "body" | "method"> {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, QueryValue | QueryValue[]>;
  /** Organisation context for staff endpoints (`X-Org-Id`). */
  orgId?: string | null;
  /** Required on consequential endpoints (submit, approve, …). */
  idempotencyKey?: string;
  /** Override the fetch implementation (tests, server components). */
  fetchImpl?: typeof fetch;
  baseUrl?: string;
}

export function buildUrl(
  path: string,
  query?: RequestOptions["query"],
  baseUrl: string = API_BASE,
): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const url = `${baseUrl}${normalized}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    const values = Array.isArray(value) ? value : [value];
    for (const v of values) {
      if (v !== undefined && v !== null && v !== "") params.append(key, String(v));
    }
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = "GET",
    body,
    query,
    orgId,
    idempotencyKey,
    fetchImpl = fetch,
    baseUrl,
    headers: extraHeaders,
    ...init
  } = options;

  const headers = new Headers(extraHeaders);
  headers.set("Accept", "application/json");
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers.set("Content-Type", "application/json");
  if (UNSAFE_METHODS.has(method)) {
    const csrf = getCookie("csrftoken");
    if (csrf) headers.set("X-CSRFToken", csrf);
  }
  if (orgId) headers.set("X-Org-Id", orgId);
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);

  let response: Response;
  try {
    response = await fetchImpl(buildUrl(path, query, baseUrl), {
      ...init,
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    });
  } catch (cause) {
    throw new ApiError(
      0,
      "network_error",
      "We couldn't reach the server. Check your connection and try again.",
      { cause: cause instanceof Error ? cause.message : String(cause) },
    );
  }

  const requestId = response.headers.get("X-Request-ID");
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let parsed: unknown = undefined;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!response.ok) {
    if (isErrorEnvelope(parsed)) {
      const e = parsed.error;
      throw new ApiError(
        response.status,
        e.code,
        e.message,
        e.details ?? {},
        e.request_id ?? requestId,
      );
    }
    throw new ApiError(
      response.status,
      response.status >= 500 ? "internal_error" : "http_error",
      "An unexpected error occurred. Please try again.",
      {},
      requestId,
    );
  }
  return parsed as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "DELETE" }),
};

/** New idempotency key per user attempt (docs/08 §3.1). */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
