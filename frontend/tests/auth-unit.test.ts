import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AllauthError,
  allauth,
  ensureCsrf,
  isAuthenticated,
  pendingFlow,
} from "@/features/auth/allauth";
import { applyServerErrors } from "@/features/auth/form-errors";
import {
  changePasswordSchema,
  codeSchema,
  loginSchema,
  registerSchema,
} from "@/features/auth/schemas";
import { canEnter, homeFor, safeNext, type Me } from "@/features/auth/session";
import { ApiError } from "@/lib/api-client";
import { isProtected, loginRedirect } from "@/proxy";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("schemas", () => {
  it("register requires matching passwords, min length and terms", () => {
    const bad = registerSchema.safeParse({
      email: "x@example.test",
      password: "short",
      confirmPassword: "other",
      acceptTerms: false,
    });
    expect(bad.success).toBe(false);
    const messages = bad.error!.issues.map((i) => i.message);
    expect(messages).toEqual(expect.arrayContaining(["passwordTooShort", "mustAcceptTerms"]));
    const ok = registerSchema.safeParse({
      email: " New@Example.test ",
      password: "a long passphrase",
      confirmPassword: "a long passphrase",
      acceptTerms: true,
    });
    expect(ok.success).toBe(true);
  });

  it("password confirmation mismatch points at confirm field", () => {
    const r = changePasswordSchema.safeParse({
      currentPassword: "x",
      newPassword: "abcdefghij",
      confirmPassword: "abcdefghik",
    });
    expect(r.error!.issues[0].path).toEqual(["confirmPassword"]);
  });

  it("login and code validation", () => {
    expect(loginSchema.safeParse({ email: "bad", password: "" }).success).toBe(false);
    expect(codeSchema.safeParse({ code: "123456" }).success).toBe(true);
    expect(codeSchema.safeParse({ code: "ab12-cd34" }).success).toBe(true);
    expect(codeSchema.safeParse({ code: "12 34" }).success).toBe(false);
  });
});

describe("allauth client", () => {
  it("fetches CSRF before unsafe calls and sends the header", async () => {
    const fetchImpl = vi
      .fn()
      .mockImplementationOnce(async () => {
        document.cookie = "csrftoken=abc123";
        return new Response("{}");
      })
      .mockResolvedValueOnce(json({ status: 200, meta: { is_authenticated: true } }));
    const resp = await allauth("/auth/login", {
      method: "POST",
      body: { email: "a", password: "b" },
      fetchImpl,
    });
    expect(fetchImpl.mock.calls[0][0]).toBe("/api/v1/csrf/");
    const [url, init] = fetchImpl.mock.calls[1];
    expect(url).toBe("/api/v1/auth/browser/v1/auth/login");
    expect((init.headers as Headers).get("X-CSRFToken")).toBe("abc123");
    expect(isAuthenticated(resp)).toBe(true);
  });

  it("returns 401 pending flows instead of throwing", async () => {
    document.cookie = "csrftoken=x";
    const fetchImpl = vi.fn().mockResolvedValue(
      json(
        {
          status: 401,
          data: { flows: [{ id: "login" }, { id: "mfa_authenticate", is_pending: true }] },
          meta: { is_authenticated: false },
        },
        401,
      ),
    );
    const resp = await allauth("/auth/login", { method: "POST", body: {}, fetchImpl });
    expect(resp.status).toBe(401);
    expect(pendingFlow(resp)).toBe("mfa_authenticate");
    expect(isAuthenticated(resp)).toBe(false);
  });

  it("throws AllauthError with field errors on 400 and friendly message on 429", async () => {
    document.cookie = "csrftoken=x";
    const fetchImpl = vi.fn().mockResolvedValueOnce(
      json(
        {
          status: 400,
          errors: [
            { code: "password_breached", message: "Breached.", param: "password" },
            { code: "x", message: "General." },
          ],
        },
        400,
      ),
    );
    const err = (await allauth("/auth/signup", { method: "POST", body: {}, fetchImpl }).catch(
      (e: unknown) => e,
    )) as AllauthError;
    expect(err).toBeInstanceOf(AllauthError);
    expect(err.fieldErrors()).toEqual({ password: ["Breached."], _form: ["General."] });
    expect(err.hasCode("password_breached")).toBe(true);

    const limited = vi.fn().mockResolvedValue(new Response("not json", { status: 429 }));
    const e2 = (await allauth("/auth/login", {
      method: "POST",
      body: {},
      fetchImpl: limited,
    }).catch((e: unknown) => e)) as AllauthError;
    expect(e2.status).toBe(429);
    expect(e2.message).toMatch(/Too many attempts/);
  });

  it("network failure becomes status 0", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("offline"));
    const err = (await allauth("/auth/session", { fetchImpl }).catch(
      (e: unknown) => e,
    )) as AllauthError;
    expect(err.status).toBe(0);
  });

  it("ensureCsrf is a no-op when the cookie exists", async () => {
    document.cookie = "csrftoken=present";
    const fetchImpl = vi.fn();
    await ensureCsrf(fetchImpl);
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

describe("applyServerErrors", () => {
  it("maps allauth params and API envelope details onto form fields", () => {
    const setError = vi.fn();
    const err = new AllauthError(
      400,
      [
        { code: "x", message: "Wrong password.", param: "current_password" },
        { code: "y", message: "Form level." },
      ],
      "fallback",
    );
    const form = applyServerErrors(err, setError, { current_password: "currentPassword" } as never);
    expect(setError).toHaveBeenCalledWith("currentPassword", {
      type: "server",
      message: "Wrong password.",
    });
    expect(form).toBe("Form level.");

    const api = new ApiError(400, "validation_error", "Invalid.", { email: ["Taken."] });
    const set2 = vi.fn();
    expect(applyServerErrors(api, set2, { email: "email" } as never)).toBeNull();
    expect(applyServerErrors(new Error("x"), vi.fn())).toMatch(/Something went wrong/);
  });
});

const baseMe = {
  id: "u1",
  email: "a@example.test",
  memberships: [],
  platform_role: "none",
  mfa: { required: false, enabled: false, grace_deadline: null, in_grace: false, enforced: false },
} as unknown as Me;

describe("session helpers", () => {
  it("homeFor routes by role and canEnter gates areas", () => {
    expect(homeFor(null)).toBe("/login");
    expect(homeFor(baseMe)).toBe("/candidate/dashboard");
    const staff = { ...baseMe, memberships: [{ role: "recruiter" }] } as unknown as Me;
    expect(homeFor(staff)).toBe("/hr/dashboard");
    const admin = { ...baseMe, platform_role: "platform_admin" } as unknown as Me;
    expect(homeFor(admin)).toBe("/admin/dashboard");
    expect(canEnter(baseMe, "hr")).toBe(false);
    expect(canEnter(staff, "hr")).toBe(true);
    expect(canEnter(admin, "admin")).toBe(true);
    expect(canEnter(baseMe, "candidate")).toBe(true);
    expect(canEnter(null, "account")).toBe(false);
  });

  it("safeNext blocks open redirects", () => {
    expect(safeNext("/hr/jobs?x=1")).toBe("/hr/jobs?x=1");
    expect(safeNext("https://evil.example")).toBeNull();
    expect(safeNext("//evil.example")).toBeNull();
    expect(safeNext("/\\evil.example")).toBeNull();
    expect(safeNext(null)).toBeNull();
  });
});

describe("proxy route guard", () => {
  it("knows protected prefixes", () => {
    expect(isProtected("/hr")).toBe(true);
    expect(isProtected("/hr/jobs")).toBe(true);
    expect(isProtected("/hrx")).toBe(false);
    expect(isProtected("/jobs")).toBe(false);
  });

  it("redirects signed-out visitors to login with next", () => {
    const req = new NextRequest("http://localhost:3000/hr/jobs?status=open");
    const res = loginRedirect(req)!;
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe(
      "http://localhost:3000/login?next=%2Fhr%2Fjobs%3Fstatus%3Dopen",
    );
  });

  it("lets requests with a session cookie or public paths through", () => {
    const withCookie = new NextRequest("http://localhost:3000/hr", {
      headers: { cookie: "sessionid=abc" },
    });
    expect(loginRedirect(withCookie)).toBeNull();
    expect(loginRedirect(new NextRequest("http://localhost:3000/jobs"))).toBeNull();
  });
});

describe("allauth client envelope fallback", () => {
  it("surfaces MHRS envelope errors (e.g. CSRF failure) instead of a generic message", async () => {
    document.cookie = "csrftoken=x";
    const fetchImpl = vi.fn().mockResolvedValue(
      json(
        {
          error: {
            code: "permission_denied",
            message: "CSRF verification failed.",
            details: { reason: "csrf" },
            request_id: "req_1",
          },
        },
        403,
      ),
    );
    const err = (await allauth("/auth/signup", { method: "POST", body: {}, fetchImpl }).catch(
      (e: unknown) => e,
    )) as AllauthError;
    expect(err.message).toBe("CSRF verification failed.");
    expect(err.hasCode("permission_denied")).toBe(true);
  });
});
