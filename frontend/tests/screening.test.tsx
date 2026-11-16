import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EvaluationPanel } from "@/features/screening/components";
import { ScreeningView } from "@/features/screening/screening-page";
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

const evaluation = (over: Record<string, unknown> = {}) => ({
  id: "e1",
  version: 2,
  status: "succeeded",
  trigger: "manual",
  band: "recommended_for_review",
  band_reasons: ["score_and_essentials"],
  created_at: "2026-11-15T10:00:00Z",
  engine_version: "1",
  config_version: "1",
  llm_used: false,
  ai_notice: "AI-assisted suggestion — requires human review",
  total_score: 84,
  coverage: 0.8,
  confidence: "high",
  flags: [],
  categories: [
    { key: "technical", label: "Technical", weight: 35, score: 85.7, points: 30 },
    { key: "answers", label: "Answers", weight: 10, score: null, points: null },
  ],
  essentials: {},
  conflicts: [],
  criteria: [
    {
      id: "cr1",
      criterion_id: "k1",
      title: "Python",
      type: "skill",
      importance: "essential",
      category: "technical",
      score: 100,
      assessable: true,
      evidence_status: "explicit",
      match_method: "exact",
      confidence: 0.95,
      rationale: "",
      flags: [],
      evidence: [
        {
          claim_id: "c1",
          question_response_id: null,
          document_id: "d1",
          page: 1,
          snippet: "Python and Django",
        },
      ],
    },
    {
      id: "cr2",
      criterion_id: "k2",
      title: "SQL",
      type: "skill",
      importance: "desirable",
      category: "technical",
      score: null,
      assessable: false,
      evidence_status: "missing",
      match_method: "none",
      confidence: 0,
      rationale: "",
      flags: [],
      evidence: [],
    },
  ],
  explanation: [
    {
      kind: "strength",
      criterion_id: "k1",
      text: "Python is stated in the CV.",
      citations: [{ claim_id: "c1", page: 1, snippet: "Python and Django" }],
    },
  ],
  summary: [],
  clarification_suggestions: [],
  ...over,
});

describe("EvaluationPanel", () => {
  it("shows the label, breakdown, cited explanation and unknown (not failed) criteria", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) => (u === "/api/v1/hr/applications/a1/evaluation/" ? { body: evaluation() } : undefined),
    );
    wrap(<EvaluationPanel appId="a1" />);
    expect(await screen.findByText("84 / 100")).toBeInTheDocument();
    expect(
      screen.getAllByText("AI-assisted suggestion — requires human review").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Recommended for review")).toBeInTheDocument();
    expect(screen.getByText("30 of 35")).toBeInTheDocument();
    expect(screen.getAllByText("Not assessable yet (weight 10)").length).toBeGreaterThan(0);
    expect(screen.getByText("No evidence yet (unknown)")).toBeInTheDocument();
    const cite = screen.getByRole("link", { name: /go to the evidence/i });
    expect(cite).toHaveAttribute("href", "#criterion-k1");
  });

  it("confirms a claim and asks for a note before marking it not supported", async () => {
    const posts: { url: string; body: unknown }[] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined),
      (u) => (u === "/api/v1/hr/applications/a1/evaluation/" ? { body: evaluation() } : undefined),
      (u, init) => {
        if (u === "/api/v1/hr/claims/c1/verify/" && init?.method === "POST") {
          posts.push({ url: u, body: JSON.parse(String(init.body)) });
          return {
            status: 201,
            body: {
              id: "v1",
              claim_id: "c1",
              decision: "confirmed",
              note: "",
              at: "2026-11-15T10:00:00Z",
              verifier: "Me",
            },
          };
        }
        return undefined;
      },
    );
    wrap(<EvaluationPanel appId="a1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Not supported" }));
    const save = screen.getByRole("button", { name: "Save and re-evaluate" });
    expect(save).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]!.body).toMatchObject({
      decision: "confirmed",
      reevaluate: true,
      criterion_result_id: "cr1",
    });
    expect(await screen.findByText(/new evaluation version/i)).toBeInTheDocument();
  });

  it("hides scores when the candidate asked for manual review, and handles not-yet-evaluated", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) =>
        u === "/api/v1/hr/applications/a1/evaluation/"
          ? { body: evaluation({ band: "manual_review_requested", total_score: null }) }
          : undefined,
    );
    wrap(<EvaluationPanel appId="a1" />);
    expect(await screen.findByText(/without software assistance/)).toBeInTheDocument();
    expect(screen.queryByText("84 / 100")).not.toBeInTheDocument();
  });

  it("says not evaluated yet on 404", async () => {
    routes((u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined));
    wrap(<EvaluationPanel appId="a1" />);
    expect(await screen.findByText("Not evaluated yet.")).toBeInTheDocument();
  });
});

describe("ScreeningView", () => {
  const analytics = {
    job_id: "j1",
    evaluated: 6,
    bands: [{ band: "review_needed", count: 6 }],
    score_buckets: Array.from({ length: 10 }, (_, i) => ({
      start: i * 10,
      end: i === 9 ? 100 : i * 10 + 9,
      count: i === 9 ? 6 : 0,
    })),
    median_score: 92.5,
    low_coverage: 6,
    high_scores: 6,
    warnings: [
      {
        code: "low_coverage",
        message: "Low evidence coverage — review the rubric or request information.",
        count: 6,
      },
    ],
    ai_notice: "AI-assisted suggestion — requires human review",
  };
  const run = {
    id: "r1",
    job_id: "j1",
    job_version_id: "v1",
    trigger: "manual",
    scope: "pending",
    reason: "",
    status: "running",
    total: 10,
    done: 4,
    failed: 1,
    progress: 0.4,
    engine_version: "1",
    config_version: "1",
    created_at: "2026-11-15T10:00:00Z",
    started_at: "2026-11-15T10:00:00Z",
    finished_at: null,
  };

  it("shows progress, warnings, a table alternative and starts a run with a reason", async () => {
    const posts: unknown[] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) =>
        u.startsWith("/api/v1/jobs/") || (u.includes("/jobs/j1/") && !u.includes("screening"))
          ? { body: { id: "j1", title: "Software Developer" } }
          : undefined,
      (u, init) => {
        if (u === "/api/v1/hr/jobs/j1/screening-runs/" && init?.method === "POST") {
          posts.push(JSON.parse(String(init.body)));
          return { status: 201, body: { ...run, total: 3, failures: [] } };
        }
        return u === "/api/v1/hr/jobs/j1/screening-runs/" ? { body: [run] } : undefined;
      },
      (u) => (u === "/api/v1/hr/jobs/j1/screening-analytics/" ? { body: analytics } : undefined),
    );
    wrap(<ScreeningView jobId="j1" />);
    const bar = await screen.findByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "40");
    expect(await screen.findByText("Low evidence coverage")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show as table" }));
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "90–100" })).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("checkbox", { name: /re-evaluate against the current vacancy version/i }),
    );
    const start = screen.getByRole("button", { name: "Start" });
    expect(start).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Reason"), "Rubric clarified");
    await userEvent.click(start);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toMatchObject({
      scope: "pending",
      use_current_version: true,
      reason: "Rubric clarified",
    });
    expect(await screen.findByText("3 applications queued.")).toBeInTheDocument();
  });

  it("is forbidden for roles without application access", async () => {
    routes((u) => (u === "/api/v1/me/" ? { body: me("panelist") } : undefined));
    wrap(<ScreeningView jobId="j1" />);
    expect(await screen.findByText(/do not have access to screening/)).toBeInTheDocument();
  });
});
