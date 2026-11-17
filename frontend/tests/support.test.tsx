import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SupportBanner } from "@/features/support/support-access";
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

describe("SupportBanner", () => {
  it("tells staff when platform support has read access", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined),
      (u) =>
        u === "/api/v1/hr/support-access/active/"
          ? { body: { active: true, until: "2026-11-17T12:00:00Z", reason: "Stuck shortlist" } }
          : undefined,
    );
    wrap(<SupportBanner />);
    expect(await screen.findByText(/temporary read-only access/)).toBeInTheDocument();
    expect(screen.getByText(/Stuck shortlist/)).toBeInTheDocument();
  });

  it("shows nothing otherwise", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined),
      (u) =>
        u === "/api/v1/hr/support-access/active/"
          ? { body: { active: false, until: null, reason: "" } }
          : undefined,
    );
    const { container } = wrap(<SupportBanner />);
    await new Promise((r) => setTimeout(r, 50));
    expect(container.textContent).toBe("");
  });
});
