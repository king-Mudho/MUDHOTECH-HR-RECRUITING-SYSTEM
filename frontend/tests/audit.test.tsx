import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuditLog } from "@/features/audit/audit-log";
import messages from "../messages/en.json";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: "j1" }),
  usePathname: () => "/hr/jobs/j1/applications",
  useSearchParams: () => new URLSearchParams(),
}));

const ORG = "11111111-1111-1111-1111-111111111111";
const me = (role: string) => ({
  id: "u1",
  email: "me@example.test",
  platform_role: "none",
  active_organisation_id: ORG,
  memberships: [
    {
      id: "m0",
      organisation_id: ORG,
      organisation_name: "Acme",
      organisation_slug: "acme",
      organisation_status: "active",
      role,
    },
  ],
  mfa: { required: false, enabled: false, grace_deadline: null, in_grace: false, enforced: false },
});

type Route = (url: string, init?: RequestInit) => unknown | undefined;
const fetchMock = vi.fn();
function routes(...handlers: Route[]) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    for (const h of handlers) {
      const r = h(url, init);
      if (r !== undefined) {
        const { status = 200, body } = r as { status?: number; body: unknown };
        return new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        });
      }
    }
    return new Response(
      JSON.stringify({ error: { code: "not_found", message: "nf", details: {}, request_id: "r" } }),
      { status: 404 },
    );
  });
}
function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="en" messages={messages} timeZone="Africa/Harare">
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  document.cookie = "csrftoken=t";
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const event = (id: string, action: string, reason = "") => ({
  id,
  created_at: "2026-11-16T10:00:00Z",
  seq: 1,
  actor: "Hope Manager",
  actor_type: "human",
  action,
  target_type: "application",
  target_id: "a1b2c3d4e5",
  before: null,
  after: null,
  reason,
  request_id: "",
  hash: "h",
});

describe("AuditLog", () => {
  it("lists events for auditors and filters by action", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("auditor") } : undefined),
      (u) =>
        u.startsWith("/api/v1/hr/audit-events/")
          ? {
              body: {
                next_cursor: null,
                previous_cursor: null,
                results: [event("e1", "shortlist.approved", "Strong evidence")],
              },
            }
          : undefined,
    );
    wrap(<AuditLog />);
    expect(await screen.findByText("shortlist.approved")).toBeInTheDocument();
    expect(screen.getByText("Strong evidence")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Action starts with"), "shortlist.");
    await userEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes("action=shortlist."))).toBe(
        true,
      ),
    );
  });

  it("is hidden from recruiters", async () => {
    routes((u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined));
    wrap(<AuditLog />);
    expect(await screen.findByText(/Only organisation admins and auditors/)).toBeInTheDocument();
  });
});
