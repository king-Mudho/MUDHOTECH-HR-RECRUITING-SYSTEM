import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HRDashboard } from "@/features/dashboard/hr-dashboard";
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

const summary = {
  cards: {
    open_vacancies: 2,
    applications_today: 1,
    applications_7d: 5,
    processing_queue: 1,
    processing_errors: 1,
    pending_reviews: 2,
    clarifications_outstanding: 0,
    shortlist_approvals_pending: 1,
  },
  ai_suggestions: {
    ai_notice: "AI-assisted suggestion — requires human review",
    bands: { review_needed: 1, lower_match: 1 },
  },
  human_decisions: { shortlisted: 1, not_selected: 0, on_hold: 0 },
  queues: {
    failed_processing: [
      {
        application_id: "a9",
        reference: "REF-9",
        job_title: "Dev",
        status: "processing_error",
        at: null,
      },
    ],
    pending_reviews: [],
    clarifications_due: [],
    approvals: [{ shortlist_id: "s1", job_id: "j1", job_title: "Dev", submitted_at: null }],
  },
};

describe("HRDashboard", () => {
  it("shows cards, AI suggestions apart from human decisions, queues and filters", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) =>
        u.startsWith("/api/v1/hr/jobs/?") || u === "/api/v1/hr/jobs/"
          ? {
              body: { count: 1, next: null, previous: null, results: [{ id: "j1", title: "Dev" }] },
            }
          : undefined,
      (u) => (u.startsWith("/api/v1/hr/dashboard/summary/") ? { body: summary } : undefined),
      (u) =>
        u === "/api/v1/hr/jobs/j1/funnel/"
          ? {
              body: {
                job_id: "j1",
                stages: [
                  { stage: "submitted", count: 4 },
                  { stage: "processed", count: 2 },
                  { stage: "reviewed", count: 1 },
                  { stage: "shortlisted", count: 1 },
                ],
                withdrawn: 0,
              },
            }
          : undefined,
    );
    wrap(<HRDashboard />);
    expect(await screen.findByText("Waiting for review")).toBeInTheDocument();
    expect(screen.getByText("AI suggestions (applications in review)")).toBeInTheDocument();
    expect(screen.getByText("Decisions made by people")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "REF-9" })).toHaveAttribute(
      "href",
      "/hr/applications/a9",
    );
    expect(screen.getByRole("link", { name: "Dev" })).toHaveAttribute(
      "href",
      "/hr/jobs/j1/shortlist",
    );
    await userEvent.selectOptions(await screen.findByLabelText("Vacancy"), "j1");
    expect(await screen.findByText("Vacancy funnel")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes("summary/?job=j1"))).toBe(true),
    );
  });
});
