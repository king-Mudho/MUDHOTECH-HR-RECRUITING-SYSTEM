import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CandidateApplicationDetail,
  CandidateApplications,
} from "@/features/candidates/components/applications";
import { CandidateDocuments } from "@/features/candidates/components/documents";
import { CandidateProfile } from "@/features/candidates/components/profile";
import messages from "../messages/en.json";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: "a1" }),
  usePathname: () => "/candidate",
  useSearchParams: () => new URLSearchParams(),
}));

type Route = (url: string, init?: RequestInit) => unknown | undefined;
const fetchMock = vi.fn();
function routes(...handlers: Route[]) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    for (const h of handlers) {
      const r = h(url, init);
      if (r !== undefined) {
        const { status = 200, body } = r as { status?: number; body: unknown };
        return new Response(status === 204 ? null : JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        });
      }
    }
    return new Response(
      JSON.stringify({
        error: { code: "not_found", message: "nf", details: {}, request_id: null },
      }),
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

const profile = {
  id: "p1",
  email: "c@example.test",
  email_verified: true,
  first_name: "Tendai",
  last_name: "M",
  preferred_name: "",
  headline: "",
  summary: "",
  city: "Harare",
  country: "ZW",
  phone_e164: "",
  links: {},
  availability: "",
  notice_period_days: null,
  open_to_relocation: false,
  profile_completeness: 5,
  missing: ["headline", "phone", "experience"],
  lock_version: 2,
  updated_at: "",
};
const app = (over: Record<string, unknown> = {}) => ({
  id: "a1",
  reference: "MHRS-ACME-2026-000001",
  status: "under_review",
  job: {
    id: "j1",
    slug: "dev-acme",
    title: "Software Developer",
    organisation_name: "Acme",
    closes_at: null,
    timezone: "Africa/Harare",
  },
  contact: {},
  last_step: 6,
  submitted_at: "2026-11-01T08:00:00Z",
  withdrawn_at: null,
  objects_to_automated_processing: false,
  notices: {
    privacy_notice: "",
    privacy_notice_version: "v",
    ai_notice_version: "v",
    ai_notice_url: "/how-we-use-ai",
  },
  lock_version: 3,
  created_at: "",
  updated_at: "",
  ...over,
});

describe("CandidateProfile", () => {
  it("shows completeness, missing items and saves with the lock version", async () => {
    routes(
      (u, i) =>
        u === "/api/v1/candidate/profile/" && i?.method === "PATCH"
          ? {
              body: {
                ...profile,
                headline: "Dev",
                lock_version: 3,
                profile_completeness: 15,
                missing: ["phone", "experience"],
              },
            }
          : undefined,
      (u) => (u === "/api/v1/candidate/profile/" ? { body: profile } : undefined),
      (u) => (u.startsWith("/api/v1/candidate/profile/") ? { body: [] } : undefined),
    );
    wrap(<CandidateProfile />);
    expect(await screen.findByText("Profile 5% complete")).toBeInTheDocument();
    expect(screen.getByText("a headline")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Headline"), "Dev");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, i]) => (i as RequestInit)?.method === "PATCH");
      expect(JSON.parse(String((patch![1] as RequestInit).body))).toMatchObject({
        headline: "Dev",
        lock_version: 2,
      });
    });
    expect(await screen.findByText("Profile 15% complete")).toBeInTheDocument();
  });

  it("adds a skill through the section form", async () => {
    routes(
      (u) => (u === "/api/v1/candidate/profile/" ? { body: profile } : undefined),
      (u, i) =>
        u === "/api/v1/candidate/profile/skills/" && i?.method === "POST"
          ? { status: 201, body: { id: "s1", raw_name: "Python" } }
          : undefined,
      (u) => (u.startsWith("/api/v1/candidate/profile/") ? { body: [] } : undefined),
    );
    wrap(<CandidateProfile />);
    const skills = (await screen.findByRole("heading", { name: "Skills" })).closest(
      "[data-slot=card]",
    ) as HTMLElement;
    await userEvent.click(within(skills).getByRole("button", { name: "Add" }));
    await userEvent.type(within(skills).getByLabelText(/Skill/), "Python");
    await userEvent.click(within(skills).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([u, i]) =>
            u === "/api/v1/candidate/profile/skills/" && (i as RequestInit)?.method === "POST",
        ),
      ).toBe(true),
    );
  });
});

describe("CandidateDocuments", () => {
  it("lists CVs with status and sets a default", async () => {
    routes(
      (u, i) =>
        u.endsWith("/set-default/") && i?.method === "POST" ? { body: profile } : undefined,
      (u) =>
        u === "/api/v1/candidate/resumes/"
          ? {
              body: [
                {
                  id: "d1",
                  original_filename: "cv-2026.pdf",
                  size_bytes: 2048,
                  page_count: 2,
                  scan_status: "clean",
                  rejected_reason: "",
                  created_at: "2026-11-01T08:00:00Z",
                  is_default: false,
                },
                {
                  id: "d2",
                  original_filename: "old.pdf",
                  size_bytes: 1024,
                  page_count: null,
                  scan_status: "infected",
                  rejected_reason: "malware",
                  created_at: "2026-10-01T08:00:00Z",
                  is_default: false,
                },
              ],
            }
          : undefined,
    );
    wrap(<CandidateDocuments />);
    expect(await screen.findByText("cv-2026.pdf")).toBeInTheDocument();
    expect(screen.getByText("Problem: upload again")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Make default" })).toHaveLength(1); // not for the rejected file
    await userEvent.click(screen.getByRole("button", { name: "Make default" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/d1/set-default/"))).toBe(true),
    );
  });
});

describe("Candidate applications", () => {
  it("lists applications and links drafts back to the wizard", async () => {
    routes((u) =>
      u === "/api/v1/applications/"
        ? { body: [app(), app({ id: "a2", status: "draft", reference: null, submitted_at: null })] }
        : undefined,
    );
    wrap(<CandidateApplications />);
    expect(await screen.findAllByText("Software Developer")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Continue application" })).toHaveAttribute(
      "href",
      "/apply/j1",
    );
    expect(screen.getByText("Under review")).toBeInTheDocument();
  });

  it("shows the timeline and withdraws with an optional reason", async () => {
    routes(
      (u, i) =>
        u.endsWith("/withdraw/") && i?.method === "POST"
          ? { body: app({ status: "withdrawn" }) }
          : undefined,
      (u) =>
        u.endsWith("/timeline/")
          ? {
              body: [
                { status: "submitted", at: "2026-11-01T08:00:00Z", note: "" },
                { status: "under_review", at: "2026-11-02T08:00:00Z", note: "" },
              ],
            }
          : undefined,
      (u) =>
        u.endsWith("/review/")
          ? {
              body: {
                application: app(),
                ready: true,
                missing: [],
                visible_questions: [],
                documents: [
                  {
                    document: "d1",
                    role: "cv",
                    required_doc_key: "cv",
                    filename: "cv.pdf",
                    scan_status: "clean",
                    size_bytes: 10,
                  },
                ],
                answers: { years: 3 },
              },
            }
          : undefined,
      (u) => (u === "/api/v1/applications/a1/" ? { body: app() } : undefined),
    );
    wrap(<CandidateApplicationDetail id="a1" />);
    expect(
      await screen.findByText("Reference MHRS-ACME-2026-000001", { exact: false }),
    ).toBeInTheDocument();
    expect(await screen.findByText("cv.pdf")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Withdraw application" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox"), "Accepted another job");
    await userEvent.click(within(dialog).getByRole("button", { name: "Withdraw application" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/withdraw/"));
      expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({
        reason: "Accepted another job",
      });
    });
  });
});
