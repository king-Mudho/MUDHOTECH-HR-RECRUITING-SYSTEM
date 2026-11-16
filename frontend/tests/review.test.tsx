import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReviewWorkspace, rememberOrder } from "@/features/screening/review-workspace";
import messages from "../messages/en.json";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
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

const crit = (id: string, title: string, over: Record<string, unknown> = {}) => ({
  id: `r-${id}`,
  criterion_id: id,
  title,
  type: "skill",
  importance: "essential",
  category: "technical",
  score: 100,
  assessable: true,
  evidence_status: "explicit",
  match_method: "exact",
  confidence: 0.9,
  rationale: "",
  flags: [],
  evidence: [],
  ...over,
});
const evaluation = (version: number, over: Record<string, unknown> = {}) => ({
  id: `e${version}`,
  version,
  status: version === 2 ? "succeeded" : "superseded",
  trigger: version === 2 ? "verification" : "auto",
  band: "recommended_for_review",
  band_reasons: [],
  created_at: "2026-11-15T10:00:00Z",
  engine_version: "1",
  config_version: "1",
  llm_used: false,
  ai_notice: "AI-assisted suggestion — requires human review",
  total_score: version === 2 ? 84 : 70,
  coverage: 1,
  confidence: "high",
  flags: [],
  categories: [],
  essentials: {},
  conflicts: [],
  criteria: [crit("k1", "Python"), crit("k2", "SQL")],
  explanation: [],
  summary: [],
  clarification_suggestions: [],
  ...over,
});
const text = "Skills: Python, Django and SQL";
const evidence = {
  application_id: "a1",
  identity_hidden: true,
  documents: [
    {
      document_id: "d1",
      filename: "CV",
      mime: "application/pdf",
      original_available: false,
      pages: [{ number: 1, text }],
      highlights: [
        { claim_id: "c1", type: "skill", page: 1, start: 8, end: 14, criteria: ["k1"] },
        { claim_id: "c2", type: "skill", page: 1, start: 27, end: 30, criteria: ["k2"] },
      ],
    },
  ],
};

describe("ReviewWorkspace", () => {
  it("highlights evidence for the chosen criterion, switches versions and supports j/k", async () => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
    rememberOrder("j1", ["a0", "a1", "a2"]);
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) => (u === "/api/v1/hr/applications/a1/evidence-text/" ? { body: evidence } : undefined),
      (u) => (u === "/api/v1/hr/applications/a1/evaluation/" ? { body: evaluation(2) } : undefined),
      (u) =>
        u === "/api/v1/hr/applications/a1/evaluations/"
          ? {
              body: [
                {
                  id: "e2",
                  version: 2,
                  status: "succeeded",
                  trigger: "verification",
                  band: "x",
                  total_score: 84,
                  created_at: "2026-11-15T10:00:00Z",
                },
                {
                  id: "e1",
                  version: 1,
                  status: "superseded",
                  trigger: "auto",
                  band: "x",
                  total_score: 70,
                  created_at: "2026-11-14T10:00:00Z",
                },
              ],
            }
          : undefined,
      (u) =>
        u === "/api/v1/hr/applications/a1/evaluations/1/" ? { body: evaluation(1) } : undefined,
    );
    wrap(<ReviewWorkspace appId="a1" jobId="j1" />);
    expect(
      await screen.findByText("Applicant 2 of 3 · press j / k for next / previous"),
    ).toBeInTheDocument();
    const python = await screen.findByText("Python", { selector: "mark" });
    expect(python).not.toHaveAttribute("data-active", "true");
    await userEvent.click(screen.getByRole("button", { name: "Python" }));
    expect(python).toHaveAttribute("data-active", "true");
    expect(screen.getByText("SQL", { selector: "mark" })).toHaveAttribute("data-active", "false");
    expect(screen.getByText("84 / 100")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Version"), "1");
    expect(await screen.findByText("70 / 100")).toBeInTheDocument();
    expect(screen.getByText(/earlier evaluation version 1/)).toBeInTheDocument();
    await userEvent.keyboard("j"); // ignored while typing in a field
    expect(push).not.toHaveBeenCalled();
    (document.activeElement as HTMLElement).blur();
    await userEvent.keyboard("j");
    expect(push).toHaveBeenCalledWith("/hr/applications/a2");
    await userEvent.keyboard("k");
    expect(push).toHaveBeenCalledWith("/hr/applications/a0");
  });
});
