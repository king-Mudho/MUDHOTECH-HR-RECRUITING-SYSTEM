import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HRApplicationView, JobApplicationsList } from "@/features/hr-applications/components";
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

const row = {
  id: "a1",
  reference: "MHRS-ACME1A2B-2026-000001",
  status: "submitted",
  submitted_at: "2026-11-01T08:00:00Z",
  candidate_name: "Rudo Moyo",
  candidate_email: "rudo@example.test",
  channel: "web",
  is_assisted: true,
  objects_to_automated_processing: false,
  identity_hidden: false,
  tags: [],
  assigned_recruiter: null,
  lock_version: 1,
  ai_band: "recommended_for_review",
  score: 84,
  coverage: 0.9,
  flags: ["low_ocr_confidence"],
  essentials: { met: 3, unknown: 1, not_evidenced: 0 },
  assigned_name: "",
};

describe("HR applications", () => {
  it("lists applicants with AI suggestions, filters by saved view and runs bulk actions", async () => {
    const bulk: unknown[] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined),
      (u) =>
        u === "/api/v1/hr/jobs/j1/"
          ? { body: { id: "j1", title: "Software Developer" } }
          : undefined,
      (u) => (u.startsWith("/api/v1/hr/saved-views/") ? { body: [] } : undefined),
      (u, init) => {
        if (u === "/api/v1/hr/jobs/j1/applications/bulk/" && init?.method === "POST") {
          bulk.push(JSON.parse(String(init.body)));
          return { body: { action: "assign_me", done: 1, skipped: [], shortlist_id: null } };
        }
        return undefined;
      },
      (u) =>
        u.startsWith("/api/v1/hr/jobs/j1/applications/")
          ? { body: { count: 1, next_cursor: null, previous_cursor: null, results: [row] } }
          : undefined,
    );
    wrap(<JobApplicationsList jobId="j1" />);
    expect(await screen.findByRole("link", { name: "Rudo Moyo" })).toHaveAttribute(
      "href",
      "/hr/applications/a1",
    );
    expect(
      within(screen.getByRole("table")).getByText("Recommended for review"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Essentials: 3 evidenced, 1 unknown, 0 weakly evidenced"),
    ).toBeInTheDocument();
    expect(screen.getByText(/AI-assisted suggestions/)).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([u]) => String(u).includes("/applications/"));
    expect(new Headers((call![1] as RequestInit).headers).get("X-Org-Id")).toBe(ORG);
    expect(String(call![0])).toContain("ordering=-score");
    await userEvent.click(screen.getByRole("button", { name: "Errors" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) => String(u).includes("status=processing_error")),
      ).toBe(true),
    );
    await userEvent.click(await screen.findByRole("checkbox", { name: "Select Rudo Moyo" }));
    await userEvent.click(screen.getByRole("button", { name: "Assign to me" }));
    await waitFor(() => expect(bulk).toEqual([{ action: "assign_me", application_ids: ["a1"] }]));
    expect(await screen.findByText("1 application updated.")).toBeInTheDocument();
  });

  it("renders only a window of rows for long lists", async () => {
    const many = Array.from({ length: 250 }, (_, i) => ({
      ...row,
      id: `a${i}`,
      candidate_name: `Candidate ${i}`,
    }));
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) => (u === "/api/v1/hr/jobs/j1/" ? { body: { id: "j1", title: "Dev" } } : undefined),
      (u) => (u.startsWith("/api/v1/hr/saved-views/") ? { body: [] } : undefined),
      (u) =>
        u.startsWith("/api/v1/hr/jobs/j1/applications/")
          ? { body: { count: 250, next_cursor: null, previous_cursor: null, results: many } }
          : undefined,
    );
    wrap(<JobApplicationsList jobId="j1" />);
    expect(await screen.findByRole("link", { name: "Candidate 0" })).toBeInTheDocument();
    const links = screen.getAllByRole("link").filter((l) => l.textContent?.startsWith("Candidate"));
    expect(links.length).toBeLessThan(40);
    expect(screen.getByText("Showing 250 of 250")).toBeInTheDocument();
  });

  it("hides the list from roles that cannot view applications", async () => {
    routes((u) => (u === "/api/v1/me/" ? { body: me("panelist") } : undefined));
    wrap(<JobApplicationsList jobId="j1" />);
    expect(
      await screen.findByText("Your role can't view applications for this vacancy."),
    ).toBeInTheDocument();
  });

  it("shows the read-only detail with documents, answers and history", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) =>
        u === "/api/v1/hr/applications/a1/"
          ? {
              body: {
                ...row,
                withdrawn_at: null,
                withdraw_reason: "",
                tags: [],
                assigned_recruiter: null,
                lock_version: 1,
                allowed_transitions: [],
                job: { id: "j1", title: "Software Developer", version: 2 },
                candidate: { email: "rudo@example.test", headline: "Developer", city: "Harare" },
                documents: [
                  {
                    id: "d1",
                    role: "cv",
                    required_doc_key: "cv",
                    filename: "cv.pdf",
                    scan_status: "clean",
                    size_bytes: 10,
                    available: true,
                  },
                ],
                answers: [
                  {
                    key: "years",
                    prompt: "Years of experience?",
                    type: "number",
                    value: 4,
                    document_id: null,
                  },
                ],
                timeline: [
                  {
                    from_status: "draft",
                    to_status: "submitted",
                    actor_type: "human",
                    reason_code: "",
                    reason_text: "",
                    at: "2026-11-01T08:00:00Z",
                  },
                ],
              },
            }
          : undefined,
    );
    wrap(<HRApplicationView id="a1" />);
    expect(await screen.findByRole("heading", { name: "Rudo Moyo" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download cv.pdf" })).toHaveAttribute(
      "href",
      "/api/v1/documents/d1/download/",
    );
    expect(screen.getByText("Years of experience?")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText(/by a person/)).toBeInTheDocument();
  });

  it("shows not found for an application outside the caller's scope", async () => {
    routes((u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined));
    wrap(<HRApplicationView id="zz" />);
    expect(await screen.findByText("Application not found")).toBeInTheDocument();
  });
});
