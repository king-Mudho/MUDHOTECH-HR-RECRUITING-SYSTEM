import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BillingRoute, usageShare } from "@/features/billing/components";
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

const overview = {
  plan: {
    code: "trial",
    name: "Free trial",
    description: "",
    limits: { active_vacancies: 2 },
    price_usd: "0.00",
    price_zwg: "0.00",
    interval: "month",
    is_trial: true,
  },
  subscription: {
    status: "trialing",
    currency: "USD",
    trial_ends_at: "2026-12-19T10:00:00Z",
    current_period_end: "2026-12-19T10:00:00Z",
    grace_until: null,
  },
  usage: [
    { metric: "active_vacancies", label: "Published vacancies", used: 2, limit: 2 },
    { metric: "seats", label: "Staff seats", used: 1, limit: 3 },
    { metric: "applications_month", label: "Applications per month", used: 12, limit: null },
  ],
  history: [],
  plans: [],
};

describe("billing", () => {
  it("computes the share of a limit", () => {
    expect(usageShare({ used: 1, limit: 4 })).toBe(0.25);
    expect(usageShare({ used: 9, limit: 4 })).toBe(1);
    expect(usageShare({ used: 3, limit: null })).toBeNull();
    expect(usageShare({ used: 0, limit: 0 })).toBe(1);
  });

  it("shows the plan, trial end and a full limit for org admins", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("org_admin") } : undefined),
      (u) => (u === "/api/v1/hr/billing/" ? { body: overview } : undefined),
    );
    wrap(<BillingRoute />);
    expect(await screen.findByText("Free trial plan")).toBeInTheDocument();
    expect(screen.getByText(/Your free trial ends on/)).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Published vacancies" })).toHaveAttribute(
      "aria-valuenow",
      "2",
    );
    expect(screen.getByText("Limit reached. Upgrade the plan to do more.")).toBeInTheDocument();
    expect(screen.getByText("12 (no limit)")).toBeInTheDocument();
  });

  it("is for organisation admins only", async () => {
    routes((u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined));
    wrap(<BillingRoute />);
    expect(
      await screen.findByText("Plan and billing are managed by organisation admins."),
    ).toBeInTheDocument();
  });
});
