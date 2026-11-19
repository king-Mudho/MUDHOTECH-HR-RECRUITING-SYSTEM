import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminDashboard, AdminTaxonomy, healthRows } from "@/features/admin/console";
import messages from "../messages/en.json";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: "j1" }),
  usePathname: () => "/hr/jobs/j1/applications",
  useSearchParams: () => new URLSearchParams(),
}));

const ORG = "11111111-1111-1111-1111-111111111111";
const me = (role: string, platform = "platform_admin") => ({
  id: "u1",
  email: "me@example.test",
  platform_role: platform,
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

describe("admin console helpers", () => {
  it("flattens health metrics and reports unavailable sources", () => {
    expect(
      healthRows({
        queues: [{ metric: "QueueDepth", value: 3, unit: "Count", dimensions: { Queue: "ai" } }],
        outbox_lag: [{ metric: "OutboxLagSeconds", value: 0, unit: "Seconds", dimensions: {} }],
        email_failure_rate: { error: "ConnectionError" },
      }),
    ).toEqual([
      { name: "QueueDepth (ai)", value: "3" },
      { name: "OutboxLagSeconds", value: "0" },
      { name: "email_failure_rate", value: "unavailable: ConnectionError" },
    ]);
  });
});

describe("AdminDashboard", () => {
  it("shows tenants, activity and health", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) =>
        u === "/api/v1/platform/overview/"
          ? {
              body: {
                tenants: { active: 3, pending_verification: 1 },
                active_vacancies: 7,
                applications_per_day: [{ day: "2026-11-19", count: 12 }],
                error_rates: {
                  dead_letters_open: 2,
                  dead_letters_24h: 1,
                  extraction_runs_24h: 10,
                  extraction_failure_rate_24h: 0.1,
                },
                health: {
                  dead_letters: [
                    { metric: "DeadLettersOpen", value: 2, unit: "Count", dimensions: {} },
                  ],
                },
              },
            }
          : undefined,
    );
    wrap(<AdminDashboard />);
    expect(await screen.findByText("Published vacancies")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument(); // tenants total
    expect(screen.getByText("10%")).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "DeadLettersOpen" })).toBeInTheDocument();
  });
});

describe("AdminTaxonomy", () => {
  it("publishes pending changes and adds aliases (platform admin)", async () => {
    const posts: [string, unknown][] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u, init) => {
        if (init?.method === "POST") {
          posts.push([u, JSON.parse(String(init.body))]);
          return { status: u.endsWith("/aliases/") ? 201 : 200, body: {} };
        }
        if (u === "/api/v1/platform/taxonomy/")
          return {
            body: {
              current_version: "2026.11.19-1",
              published_at: "2026-11-19T10:00:00Z",
              unpublished_changes: true,
              skills: 1,
              versions: [],
            },
          };
        if (u.startsWith("/api/v1/platform/taxonomy/skills/"))
          return {
            body: [
              {
                id: "s1",
                canonical_name: "Python",
                category: "software_it",
                is_active: true,
                taxonomy_version: "2026.11.19-1",
                aliases: [{ id: "a1", alias: "py" }],
                relations: [],
              },
            ],
          };
        if (u.startsWith("/api/v1/platform/taxonomy/qualifications/")) return { body: [] };
        return undefined;
      },
    );
    wrap(<AdminTaxonomy />);
    expect(
      await screen.findByText("There are changes that are not published yet."),
    ).toBeInTheDocument();
    await userEvent.type(await screen.findByLabelText("New alias for Python"), "python3");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    await userEvent.click(screen.getByRole("button", { name: "Publish new version" }));
    await waitFor(() =>
      expect(posts.map((p) => p[0])).toEqual([
        "/api/v1/platform/taxonomy/skills/s1/aliases/",
        "/api/v1/platform/taxonomy/",
      ]),
    );
  });
});
