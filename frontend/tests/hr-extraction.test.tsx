import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { HRApplicationDetail } from "@/features/hr-applications/api";
import { ExtractionPanel } from "@/features/hr-applications/extraction-panel";
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

const app = { id: "a1" } as HRApplicationDetail;
const claim = (id: string, type: string, title: string, extra: Record<string, unknown> = {}) => ({
  id,
  index: 0,
  type,
  title,
  subtitle: "",
  dates: "",
  detail: "",
  snippet: `${title} line`,
  page: 1,
  excluded: false,
  excluded_reason: "",
  section: "experience",
  method: "rule",
  confidence: "high",
  inferred: false,
  corrections: [],
  ...extra,
});
const panel = (over: Record<string, unknown> = {}) => ({
  application_id: "a1",
  status: "processing",
  flags: ["identity_mismatch_possible"],
  manual_review_requested: false,
  can_retry: false,
  runs: [
    {
      id: "r1",
      document_id: "d1",
      filename: "cv.pdf",
      status: "succeeded",
      error_code: "",
      flags: ["hidden_text"],
      language: "en",
      quality_score: 0.9,
      page_count: 2,
      attempts: 1,
      finished_at: "2026-11-15T10:00:00Z",
      set_aside: 7,
      claims: [
        claim("c1", "experience", "Software Developer", {
          subtitle: "Granite Labs",
          corrections: [
            {
              id: "x1",
              status: "pending",
              created_at: "2026-11-15T10:00:00Z",
              values: { title: "Lead Developer" },
              remove: false,
              note: "Promoted",
            },
          ],
        }),
        claim("c2", "skill", "Python", { confidence: "low", inferred: true }),
      ],
    },
  ],
  ...over,
});

describe("ExtractionPanel", () => {
  it("shows evidence, flags in plain words, corrections and the AI label", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) => (u === "/api/v1/hr/applications/a1/extraction/" ? { body: panel() } : undefined),
    );
    wrap(<ExtractionPanel app={app} />);
    expect(await screen.findByText("Software Developer")).toBeInTheDocument();
    expect(screen.getByText(/AI-assisted suggestion — requires human review/)).toBeInTheDocument();
    expect(screen.getByText(/name on the CV is different/)).toBeInTheDocument();
    expect(screen.getByText(/hidden text/)).toBeInTheDocument();
    expect(screen.getByText(/title: Lead Developer/)).toBeInTheDocument();
    expect(screen.getByText("Uncertain")).toBeInTheDocument();
    expect(screen.getByText(/7 items were set aside/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry processing" })).not.toBeInTheDocument();
    const sent = fetchMock.mock.calls.find(([u]) => String(u).includes("/extraction/"));
    expect(new Headers((sent?.[1] as RequestInit).headers).get("X-Org-Id")).toBe(ORG);
  });

  it("lets editors retry a failed read; hiring managers don't get the button", async () => {
    const failed = panel({
      status: "processing_error",
      can_retry: true,
      flags: [],
      runs: [
        { ...panel().runs[0], status: "failed", error_code: "corrupt", claims: [], flags: [] },
      ],
    });
    let retried = false;
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined),
      (u, init) => {
        if (u === "/api/v1/hr/applications/a1/retry-processing/" && init?.method === "POST") {
          retried = true;
          return { body: panel({ can_retry: false }) };
        }
        return u === "/api/v1/hr/applications/a1/extraction/" ? { body: failed } : undefined;
      },
    );
    wrap(<ExtractionPanel app={app} />);
    expect(await screen.findByText("The CV could not be read")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry processing" }));
    await waitFor(() => expect(retried).toBe(true));
    expect(await screen.findByText("Software Developer")).toBeInTheDocument();
  });

  it("hides retry from hiring managers", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hiring_manager") } : undefined),
      (u) =>
        u === "/api/v1/hr/applications/a1/extraction/"
          ? { body: panel({ can_retry: true }) }
          : undefined,
    );
    wrap(<ExtractionPanel app={app} />);
    expect(await screen.findByText("Software Developer")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry processing" })).not.toBeInTheDocument();
  });
});
