import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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
};

describe("HR applications", () => {
  it("lists applications, sends the org header and filters by status", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined),
      (u) =>
        u === "/api/v1/hr/jobs/j1/"
          ? { body: { id: "j1", title: "Software Developer" } }
          : undefined,
      (u) =>
        u.startsWith("/api/v1/hr/jobs/j1/applications/")
          ? { body: { count: 1, results: [row] } }
          : undefined,
    );
    wrap(<JobApplicationsList jobId="j1" />);
    expect(await screen.findByRole("link", { name: "Rudo Moyo" })).toHaveAttribute(
      "href",
      "/hr/applications/a1",
    );
    expect(screen.getByText("Assisted")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([u]) => String(u).includes("/applications/"));
    expect(new Headers((call![1] as RequestInit).headers).get("X-Org-Id")).toBe(ORG);
    await userEvent.click(screen.getByRole("button", { name: "Withdrawn" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes("status=withdrawn"))).toBe(true),
    );
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
