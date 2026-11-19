import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { formatHours, percent, ReportsRoute } from "@/features/reports/components";
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

const dur = (median: number | null, count = 2) => ({
  count,
  median_hours: median,
  mean_hours: median,
  p90_hours: median,
});
const report = {
  scope: { from: "2026-08-22", to: "2026-11-19", department: null, job: null },
  computed_at: "2026-11-19T10:00:00Z",
  origin: "live",
  applications: 4,
  timing: {
    time_to_review: dur(20),
    time_to_shortlist: dur(30),
    time_to_hire: dur(96, 1),
  },
  funnel: {
    stages: [
      { stage: "submitted", count: 4, conversion: null },
      { stage: "reviewed", count: 3, conversion: 0.75 },
      { stage: "shortlisted", count: 2, conversion: 0.6667 },
      { stage: "interviewed", count: 1, conversion: 0.5 },
      { stage: "offered", count: 1, conversion: 1 },
      { stage: "hired", count: 1, conversion: 1 },
    ],
    withdrawn: 0,
  },
  sources: [
    { source: "linkedin", applications: 2, shortlisted: 2 },
    { source: "direct", applications: 2, shortlisted: 0 },
  ],
  questionnaire: {
    started: 7,
    submitted: 4,
    unfinished: 3,
    unfinished_by_step: [
      { step: "contact", unfinished: 1 },
      { step: "profile", unfinished: 0 },
      { step: "documents", unfinished: 2 },
      { step: "questions", unfinished: 0 },
      { step: "review", unfinished: 0 },
    ],
    questions: [],
  },
  processing: {
    extraction_runs: 3,
    parse_failure_rate: 0.3333,
    partial_rate: 0,
    ocr_rate: 0.3333,
    mean_extraction_seconds: 20,
    submission_to_evaluation: dur(0.5),
  },
  ai_agreement: {
    decisions: 3,
    overrides: 2,
    override_rate: 0.6667,
    agreement_rate: 0.3333,
    by_band: [{ band: "lower_match", decisions: 1, overrides: 1, override_rate: 1 }],
    by_job: [{ job_id: "j1", decisions: 3, overrides: 2, override_rate: 0.6667 }],
    claim_verification_override_rate: null,
    evaluations: 3,
  },
  clarifications: {
    total: 2,
    answered: 1,
    expired: 1,
    open: 0,
    cancelled: 0,
    response_rate: 0.5,
    time_to_answer: dur(5, 1),
  },
};

describe("report helpers", () => {
  it("formats durations and rates", () => {
    expect(formatHours(null)).toBe("—");
    expect(formatHours(3.46)).toBe("3.5 h");
    expect(formatHours(96)).toBe("4 d");
    expect(percent(0.6667)).toBe("66.7%");
    expect(percent(undefined)).toBe("—");
  });
});

describe("ReportsRoute", () => {
  it("shows every section with table views and drills down into a vacancy", async () => {
    const calls: string[] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) =>
        u.startsWith("/api/v1/hr/jobs/")
          ? {
              body: { count: 1, next: null, previous: null, results: [{ id: "j1", title: "Dev" }] },
            }
          : undefined,
      (u) =>
        u.includes("/departments/")
          ? { body: { count: 0, next: null, previous: null, results: [] } }
          : undefined,
      (u) => {
        if (!u.startsWith("/api/v1/hr/reports/recruitment/")) return undefined;
        calls.push(u);
        return { body: report };
      },
    );
    wrap(<ReportsRoute />);
    expect(await screen.findByRole("heading", { name: "Funnel" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Hired" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Direct / not tagged" })).toBeInTheDocument();
    expect(screen.getByText("4 d")).toBeInTheDocument();
    expect(screen.getAllByText("66.7%").length).toBeGreaterThan(0);
    expect(screen.getByText(/AI-assisted suggestion — requires human review/)).toBeInTheDocument();
    expect(screen.getAllByRole("table").length).toBeGreaterThanOrEqual(4);
    await userEvent.click(screen.getByRole("button", { name: "Dev" }));
    await waitFor(() => expect(calls.some((u) => u.includes("job=j1"))).toBe(true));
  });

  it("is limited to HR managers and admins", async () => {
    routes((u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined));
    wrap(<ReportsRoute />);
    expect(
      await screen.findByText("Reports are available to HR managers and organisation admins."),
    ).toBeInTheDocument();
  });
});
