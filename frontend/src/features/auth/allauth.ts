/**
 * Typed client for django-allauth headless (browser client) at /api/v1/auth/browser/v1.
 *
 * allauth uses its own response format (not the MHRS error envelope):
 *   200 -> { status, data, meta }
 *   400 -> { status, errors: [{ code, message, param? }] }
 *   401 -> { status, data: { flows: [...] }, meta: { is_authenticated } }  (a flow is pending, e.g.
 *          verify_email, mfa_authenticate, reauthenticate) - NOT a failure for the caller to show.
 *   409/410/429 -> conflict / expired / rate limited
 * Session cookies + CSRF header only; tokens never touch JS storage (ADR-004).
 */

import { getCookie } from "@/lib/api-client";

export const ALLAUTH_BASE = "/api/v1/auth/browser/v1";

export type FlowId =
  | "login"
  | "signup"
  | "verify_email"
  | "mfa_authenticate"
  | "reauthenticate"
  | "mfa_reauthenticate"
  | "password_reset_by_code";

export interface AllauthFlow {
  id: FlowId | string;
  is_pending?: boolean;
}

export interface AllauthErrorItem {
  code: string;
  message: string;
  param?: string;
}

export interface AllauthResponse<T = Record<string, unknown>> {
  status: number;
  data?: T & { flows?: AllauthFlow[] };
  meta?: { is_authenticated?: boolean; [key: string]: unknown };
  errors?: AllauthErrorItem[];
}

export class AllauthError extends Error {
  readonly status: number;
  readonly errors: AllauthErrorItem[];

  constructor(status: number, errors: AllauthErrorItem[], fallback: string) {
    super(errors[0]?.message ?? fallback);
    this.name = "AllauthError";
    this.status = status;
    this.errors = errors;
  }

  /** `{ field: [messages] }`; errors without `param` go to `_form`. */
  fieldErrors(): Record<string, string[]> {
    const out: Record<string, string[]> = {};
    for (const e of this.errors) {
      const key = e.param ?? "_form";
      (out[key] ??= []).push(e.message);
    }
    return out;
  }

  hasCode(code: string): boolean {
    return this.errors.some((e) => e.code === code);
  }
}

let csrfPromise: Promise<void> | null = null;

/** Ensure the `csrftoken` cookie exists (Django sets it via GET /api/v1/csrf/). */
export function ensureCsrf(fetchImpl: typeof fetch = fetch): Promise<void> {
  if (getCookie("csrftoken")) return Promise.resolve();
  csrfPromise ??= fetchImpl("/api/v1/csrf/", { credentials: "same-origin" })
    .then(() => undefined)
    .finally(() => {
      csrfPromise = null;
    });
  return csrfPromise;
}

export interface CallOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  fetchImpl?: typeof fetch;
}

/**
 * Perform an allauth call. Resolves for 2xx and 401 (pending flow / unauthenticated); throws
 * `AllauthError` for 4xx/5xx with errors.
 */
export async function allauth<T = Record<string, unknown>>(
  path: string,
  { method = "GET", body, headers = {}, fetchImpl = fetch }: CallOptions = {},
): Promise<AllauthResponse<T>> {
  if (method !== "GET") await ensureCsrf(fetchImpl);
  const h = new Headers({ Accept: "application/json", ...headers });
  if (body !== undefined) h.set("Content-Type", "application/json");
  const csrf = getCookie("csrftoken");
  if (csrf && method !== "GET") h.set("X-CSRFToken", csrf);

  let res: Response;
  try {
    res = await fetchImpl(`${ALLAUTH_BASE}${path}`, {
      method,
      headers: h,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new AllauthError(0, [], "We couldn't reach the server. Check your connection.");
  }
  let json: AllauthResponse<T>;
  try {
    json = (await res.json()) as AllauthResponse<T>;
  } catch {
    json = { status: res.status };
  }
  if (res.ok || res.status === 401) return { ...json, status: res.status };
  // Django-level failures (CSRF, MFA enforcement) come back in the MHRS error envelope.
  const envelope = (json as { error?: { code?: string; message?: string } }).error;
  const fallback =
    res.status === 429
      ? "Too many attempts. Please wait a moment and try again."
      : (envelope?.message ?? "Something went wrong. Please try again.");
  const errors =
    json.errors ?? (envelope?.code ? [{ code: envelope.code, message: fallback }] : []);
  throw new AllauthError(res.status, errors, fallback);
}

export function pendingFlow<T>(resp: AllauthResponse<T>): FlowId | string | null {
  return resp.data?.flows?.find((f) => f.is_pending)?.id ?? null;
}

export const isAuthenticated = <T>(resp: AllauthResponse<T>) =>
  resp.meta?.is_authenticated === true;

// --------------------------------------------------------------------- endpoint helpers
export const authApi = {
  session: () => allauth("/auth/session"),
  login: (email: string, password: string) =>
    allauth("/auth/login", { method: "POST", body: { email, password } }),
  logout: () => allauth("/auth/session", { method: "DELETE" }),
  signup: (email: string, password: string) =>
    allauth("/auth/signup", { method: "POST", body: { email, password } }),
  verifyEmail: (key: string) => allauth("/auth/email/verify", { method: "POST", body: { key } }),
  resendVerification: () => allauth("/auth/email/verify/resend", { method: "POST" }),
  requestPasswordReset: (email: string) =>
    allauth("/auth/password/request", { method: "POST", body: { email } }),
  resetPassword: (key: string, password: string) =>
    allauth("/auth/password/reset", { method: "POST", body: { key, password } }),
  changePassword: (current_password: string, new_password: string) =>
    allauth("/account/password/change", {
      method: "POST",
      body: { current_password, new_password },
    }),
  changeEmail: (email: string) => allauth("/account/email", { method: "POST", body: { email } }),
  mfaAuthenticate: (code: string) =>
    allauth("/auth/2fa/authenticate", { method: "POST", body: { code } }),
  reauthenticate: (password: string) =>
    allauth("/auth/reauthenticate", { method: "POST", body: { password } }),
  authenticators: () => allauth<AuthenticatorItem[]>("/account/authenticators"),
  totpStatus: () => allauth<TotpData>("/account/authenticators/totp"),
  activateTotp: (code: string) =>
    allauth("/account/authenticators/totp", { method: "POST", body: { code } }),
  deactivateTotp: () => allauth("/account/authenticators/totp", { method: "DELETE" }),
  recoveryCodes: () => allauth<RecoveryCodesData>("/account/authenticators/recovery-codes"),
  regenerateRecoveryCodes: () =>
    allauth<RecoveryCodesData>("/account/authenticators/recovery-codes", { method: "POST" }),
};

export interface AuthenticatorItem {
  type: "totp" | "recovery_codes" | string;
  created_at?: number;
  last_used_at?: number | null;
}

export interface TotpData {
  type?: string;
}

export interface RecoveryCodesData {
  type?: string;
  total_code_count?: number;
  unused_code_count?: number;
  unused_codes?: string[];
}
