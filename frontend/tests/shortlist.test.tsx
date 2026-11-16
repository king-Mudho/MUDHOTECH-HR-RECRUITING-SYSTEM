import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ShortlistBuilder, columnOf, isOverride } from "@/features/shortlisting/builder";
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

const entry = (id: string, name: string, band: string, over: Record<string, unknown> = {}) => ({
  id: `e-${id}`,
  application_id: id,
  reference: `REF-${id}`,
  candidate_name: name,
  identity_hidden: false,
  status: "under_review",
  suggestion: band === "recommended_for_review" ? "shortlist" : "",
  decision: "undecided",
  reason_code: "",
  reason_text: "",
  ai_band: band,
  score: 80,
  coverage: 0.9,
  override: false,
  decided_by: null,
  decided_at: null,
  applied_at: null,
  apply_note: "",
  ...over,
});
const summary = (over: Record<string, unknown> = {}) => ({
  total: 3,
  undecided: 3,
  shortlist: 0,
  not_selected: 0,
  hold: 0,
  overrides: 0,
  low_coverage: 1,
  uncertain_not_selected: 0,
  reasons: {},
  above_desired_size: false,
  ...over,
});
const shortlist = (over: Record<string, unknown> = {}) => ({
  id: "s1",
  job_id: "j1",
  job_version_id: "v1",
  status: "draft",
  desired_size: 2,
  proposed_by: "Rec",
  proposed_by_id: "u2",
  submitted_at: null,
  approved_at: null,
  notify_after: null,
  return_reason: "",
  undo_reason: "",
  notes: "",
  lock_version: 3,
  created_at: "2026-11-16T10:00:00Z",
  summary: summary(),
  entries: [
    entry("a1", "Ann", "recommended_for_review"),
    entry("a2", "Ben", "review_needed", { coverage: 0.4 }),
    entry("a3", "Cara", "lower_match"),
  ],
  ...over,
});
const reasons = [
  {
    code: "less_relevant_experience",
    label: "Less relevant experience",
    applies_to: "not_selected",
  },
  { code: "evidence_review_differs", label: "Evidence review differs", applies_to: "override" },
  { code: "meets_essential", label: "Meets essentials", applies_to: "shortlist" },
];

describe("shortlist helpers", () => {
  it("puts applicants in columns and recognises overrides", () => {
    expect(columnOf(entry("a", "A", "recommended_for_review") as never)).toBe("suggested");
    expect(columnOf(entry("a", "A", "review_needed", { coverage: 0.4 }) as never)).toBe("low");
    expect(columnOf(entry("a", "A", "eligibility_review") as never)).toBe("review");
    expect(columnOf(entry("a", "A", "lower_match") as never)).toBe("others");
    expect(isOverride("shortlist", "lower_match")).toBe(true);
    expect(isOverride("not_selected", "recommended_for_review")).toBe(true);
    expect(isOverride("hold", "recommended_for_review")).toBe(false);
  });
});

describe("ShortlistBuilder", () => {
  it("records decisions with reasons (override needs a reason)", async () => {
    const patches: unknown[] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined),
      (u) => (u === "/api/v1/hr/jobs/j1/" ? { body: { id: "j1", title: "Dev" } } : undefined),
      (u) => (u === "/api/v1/hr/jobs/j1/shortlists/" ? { body: [shortlist()] } : undefined),
      (u) => (u.startsWith("/api/v1/hr/decision-reasons/") ? { body: reasons } : undefined),
      (u, init) => {
        if (u === "/api/v1/hr/shortlists/s1/entries/" && init?.method === "PATCH") {
          patches.push(JSON.parse(String(init.body)));
          return { body: shortlist() };
        }
        return u === "/api/v1/hr/shortlists/s1/" ? { body: shortlist() } : undefined;
      },
    );
    wrap(<ShortlistBuilder jobId="j1" />);
    expect(await screen.findByText("3 undecided", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Low evidence coverage (1)" })).toBeInTheDocument();
    const ann = within(screen.getByRole("group", { name: "Decision for Ann" }));
    await userEvent.click(ann.getByRole("button", { name: "Shortlist" }));
    await waitFor(() =>
      expect(patches[0]).toEqual({
        decisions: [
          { application_id: "a1", decision: "shortlist", reason_code: "", reason_text: "" },
        ],
        lock_version: 3,
      }),
    );
    const cara = within(screen.getByRole("group", { name: "Decision for Cara" }));
    await userEvent.click(cara.getByRole("button", { name: "Shortlist" }));
    expect(screen.getByText(/differs from the AI suggestion — please say why/)).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Save decision" });
    expect(save).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Reason"), "evidence_review_differs");
    await userEvent.click(save);
    await waitFor(() => expect(patches).toHaveLength(2));
    expect(patches[1]).toMatchObject({
      decisions: [
        { application_id: "a3", decision: "shortlist", reason_code: "evidence_review_differs" },
      ],
    });
  });

  it("approval needs the undecided ones acknowledged and sends an idempotency key", async () => {
    const posts: { url: string; key: string | null; body: unknown }[] = [];
    const pending = shortlist({
      status: "pending_approval",
      summary: summary({ shortlist: 2, undecided: 1, not_selected: 0 }),
    });
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) => (u === "/api/v1/hr/jobs/j1/" ? { body: { id: "j1", title: "Dev" } } : undefined),
      (u) => (u === "/api/v1/hr/jobs/j1/shortlists/" ? { body: [pending] } : undefined),
      (u) => (u.startsWith("/api/v1/hr/decision-reasons/") ? { body: reasons } : undefined),
      (u, init) => {
        if (u === "/api/v1/hr/shortlists/s1/approve/" && init?.method === "POST") {
          posts.push({
            url: u,
            key: new Headers(init.headers).get("Idempotency-Key"),
            body: JSON.parse(String(init.body)),
          });
          return { body: { ...pending, status: "approved" } };
        }
        return u === "/api/v1/hr/shortlists/s1/" ? { body: pending } : undefined;
      },
    );
    wrap(<ShortlistBuilder jobId="j1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve shortlist" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Approve" });
    expect(confirm).toBeDisabled();
    await userEvent.click(
      within(dialog).getByRole("checkbox", { name: /Leave 1 undecided applicant/ }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]!.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(posts[0]!.body).toEqual({ lock_version: 3, leave_undecided: true });
  });
});
