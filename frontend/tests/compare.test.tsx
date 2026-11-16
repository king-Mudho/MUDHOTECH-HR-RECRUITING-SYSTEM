import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompareView } from "@/features/screening/compare";
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

const detail = (id: string, name: string) => ({
  id,
  reference: `REF-${id}`,
  candidate_name: name,
  identity_hidden: false,
});

describe("CompareView", () => {
  it("shows criteria rows for each applicant and hides AI output for manual review", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) => (u === "/api/v1/hr/applications/a1/" ? { body: detail("a1", "Ann") } : undefined),
      (u) => (u === "/api/v1/hr/applications/a2/" ? { body: detail("a2", "Ben") } : undefined),
      (u) =>
        u === "/api/v1/hr/applications/a1/evaluation/"
          ? {
              body: evaluation(2, {
                criteria: [
                  crit("k1", "Python", {
                    evidence: [
                      {
                        claim_id: "c1",
                        question_response_id: null,
                        document_id: "d",
                        page: 1,
                        snippet: "Python 5 years",
                      },
                    ],
                  }),
                ],
              }),
            }
          : undefined,
      (u) =>
        u === "/api/v1/hr/applications/a2/evaluation/"
          ? { body: evaluation(2, { band: "manual_review_requested", total_score: null }) }
          : undefined,
    );
    wrap(<CompareView ids={["a1", "a2"]} />);
    expect(await screen.findByRole("columnheader", { name: /Ann/ })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: /Python/ })).toBeInTheDocument();
    expect(screen.getByText("84 / 100")).toBeInTheDocument();
    expect(screen.getByText("Manual review requested")).toBeInTheDocument();
    expect(screen.getByText("1 evidence snippet")).toBeInTheDocument();
    expect(screen.getByText("“Python 5 years”")).toBeInTheDocument();
  });

  it("asks for at least two applicants", async () => {
    routes((u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined));
    wrap(<CompareView ids={["a1"]} />);
    expect(await screen.findByText("Choose applicants to compare")).toBeInTheDocument();
  });
});
