import { afterEach, describe, expect, it, vi } from "vitest";

import { shouldRetry } from "@/app/providers";
import {
  ApiError,
  api,
  apiRequest,
  buildUrl,
  getCookie,
  isErrorEnvelope,
  newIdempotencyKey,
} from "@/lib/api-client";
import type { paths } from "@/types/api";

type ApiRoot = paths["/api/v1/"]["get"]["responses"][200]["content"]["application/json"];

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

afterEach(() => {
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("buildUrl", () => {
  it("prefixes the API base and serialises query params", () => {
    expect(buildUrl("jobs/", { q: "dev", page: 2, empty: "", none: null, tag: ["a", "b"] })).toBe(
      "/api/v1/jobs/?q=dev&page=2&tag=a&tag=b",
    );
    expect(buildUrl("/me")).toBe("/api/v1/me");
  });
});

describe("getCookie", () => {
  it("reads and decodes cookies", () => {
    expect(getCookie("csrftoken", "a=1; csrftoken=abc%3D; b=2")).toBe("abc=");
    expect(getCookie("missing", "a=1")).toBeNull();
  });
});

describe("apiRequest", () => {
  it("returns typed JSON on success using generated types", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({
        name: "MUDHOTECH HR RECRUITING SYSTEM",
        version: "1.0.0",
        server_time: "x",
      }),
    );
    const data = await api.get<ApiRoot>("/", { fetchImpl });
    expect(data.name).toBe("MUDHOTECH HR RECRUITING SYSTEM");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("/api/v1/");
    expect(init.credentials).toBe("same-origin");
    expect((init.headers as Headers).get("X-CSRFToken")).toBeNull();
  });

  it("sends CSRF, org and idempotency headers on unsafe methods", async () => {
    document.cookie = "csrftoken=tok123";
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ ok: true }, 201));
    await api.post(
      "/applications/1/submit/",
      { a: 1 },
      {
        fetchImpl,
        orgId: "org-1",
        idempotencyKey: "key-1",
      },
    );
    const init = fetchImpl.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Headers;
    expect(headers.get("X-CSRFToken")).toBe("tok123");
    expect(headers.get("X-Org-Id")).toBe("org-1");
    expect(headers.get("Idempotency-Key")).toBe("key-1");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ a: 1 }));
    expect(init.method).toBe("POST");
  });

  it("does not JSON-encode FormData", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({}, 200));
    const form = new FormData();
    form.append("f", "v");
    await apiRequest("/x/", { method: "POST", body: form, fetchImpl });
    const init = fetchImpl.mock.calls[0][1] as RequestInit;
    expect(init.body).toBe(form);
    expect((init.headers as Headers).get("Content-Type")).toBeNull();
  });

  it("parses the error envelope into ApiError with field errors", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "validation_error",
            message: "Some fields are invalid.",
            details: { closes_at: ["Must be in the future."], title: "Required." },
            request_id: "req_ABC",
          },
        },
        400,
      ),
    );
    const err = await api.patch("/jobs/1/", {}, { fetchImpl }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const apiErr = err as ApiError;
    expect(apiErr.status).toBe(400);
    expect(apiErr.code).toBe("validation_error");
    expect(apiErr.requestId).toBe("req_ABC");
    expect(apiErr.fieldErrors()).toEqual({
      closes_at: ["Must be in the future."],
      title: ["Required."],
    });
  });

  it("falls back to the X-Request-ID header for non-envelope errors", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response("<html>bad gateway</html>", {
        status: 502,
        headers: { "X-Request-ID": "req_HDR" },
      }),
    );
    const err = (await api.delete("/x/", { fetchImpl }).catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("internal_error");
    expect(err.requestId).toBe("req_HDR");
  });

  it("maps 4xx without envelope to http_error and 204 to undefined", async () => {
    const f1 = vi.fn().mockResolvedValue(new Response("", { status: 404 }));
    const err = (await api.get("/x/", { fetchImpl: f1 }).catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("http_error");
    const f2 = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api.put("/x/", {}, { fetchImpl: f2 })).resolves.toBeUndefined();
  });

  it("wraps network failures", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const err = (await api.get("/x/", { fetchImpl }).catch((e: unknown) => e)) as ApiError;
    expect(err.isNetworkError).toBe(true);
    expect(err.code).toBe("network_error");
  });
});

describe("helpers", () => {
  it("isErrorEnvelope guards shape", () => {
    expect(isErrorEnvelope({ error: { code: "x", message: "y" } })).toBe(true);
    expect(isErrorEnvelope({ error: "x" })).toBe(false);
    expect(isErrorEnvelope(null)).toBe(false);
  });

  it("newIdempotencyKey returns UUIDs", () => {
    expect(newIdempotencyKey()).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("does not retry client errors", () => {
    expect(shouldRetry(0, new ApiError(404, "not_found", "x"))).toBe(false);
    expect(shouldRetry(0, new ApiError(503, "x", "x"))).toBe(true);
    expect(shouldRetry(2, new Error("x"))).toBe(false);
  });
});
