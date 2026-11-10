import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { visibleKeys, wordCount } from "@/features/apply/visibility";
import { ApplyWizard } from "@/features/apply/wizard";
import messages from "../messages/en.json";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/apply/j1",
  useSearchParams: () => new URLSearchParams("utm_source=whatsapp"),
}));

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
  push.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const job = {
  id: "j1",
  title: "Software Developer",
  organisation: { slug: "acme", name: "Acme", logo_url: null, verified: true },
  closes_at: "2026-12-01T15:00:00Z",
  timezone: "Africa/Harare",
  accepts_applications: true,
  required_documents: ["cv"],
};
const questions = [
  {
    key: "has_degree",
    section: "",
    type: "yes_no",
    prompt: "Do you have a degree?",
    help_text: "",
    required: true,
    config: {},
    branching: {},
    options: [],
  },
  {
    key: "degree_name",
    section: "",
    type: "short_text",
    prompt: "Which degree?",
    help_text: "",
    required: false,
    config: {},
    branching: { show_if: { question: "has_degree", op: "eq", value: "yes" } },
    options: [],
  },
];
const app = (over: Record<string, unknown> = {}) => ({
  id: "a1",
  reference: null,
  status: "draft",
  job: { id: "j1", slug: "dev", title: "Software Developer", organisation_name: "Acme" },
  contact: {},
  last_step: 5,
  notices: { privacy_notice: "", privacy_notice_version: "v", ai_notice_version: "v" },
  lock_version: 1,
  ...over,
});
const review = (over: Record<string, unknown> = {}) => ({
  application: app(),
  ready: true,
  missing: [],
  visible_questions: ["has_degree"],
  documents: [
    {
      document: "d1",
      role: "cv",
      required_doc_key: "cv",
      filename: "cv.pdf",
      scan_status: "clean",
      size_bytes: 9,
    },
  ],
  answers: { has_degree: "no" },
  ...over,
});
const base: Route[] = [
  (u) => (u === "/api/v1/jobs/j1/" ? { body: job } : undefined),
  (u) => (u === "/api/v1/jobs/j1/questions/" ? { body: questions } : undefined),
  (u, i) =>
    u === "/api/v1/applications/a1/" && i?.method === "PATCH" ? { body: app() } : undefined,
  (u) =>
    u === "/api/v1/candidate/profile/"
      ? { body: { email: "c@example.test", first_name: "T" } }
      : undefined,
  (u) => (u === "/api/v1/candidate/resumes/" ? { body: [] } : undefined),
];

describe("visibility helpers", () => {
  it("shows a follow-up only when its parent matches", () => {
    expect(visibleKeys(questions, {})).toEqual(["has_degree"]);
    expect(visibleKeys(questions, { has_degree: "yes" })).toEqual(["has_degree", "degree_name"]);
    expect(wordCount("  two words ")).toBe(2);
    expect(wordCount("")).toBe(0);
  });
});

describe("ApplyWizard", () => {
  it("EC-APP-06: resumes at the saved step, needs consent, submits with an idempotency key and shows the reference", async () => {
    routes(
      ...base,
      (u, i) =>
        u === "/api/v1/applications/" && i?.method === "POST"
          ? { status: 201, body: app() }
          : undefined,
      (u) => (u === "/api/v1/applications/a1/review/" ? { body: review() } : undefined),
      (u, i) =>
        u === "/api/v1/applications/a1/submit/" && i?.method === "POST"
          ? {
              body: {
                id: "a1",
                reference: "MHRS-ACME-2026-000007",
                status: "submitted",
                submitted_at: "",
              },
            }
          : undefined,
    );
    wrap(<ApplyWizard jobId="j1" />);
    expect(await screen.findByText("Step 5 of 5 — Review & submit")).toBeInTheDocument();
    const start = fetchMock.mock.calls.find(
      ([u, i]) => u === "/api/v1/applications/" && i?.method === "POST",
    );
    expect(JSON.parse(String((start![1] as RequestInit).body))).toEqual({
      job_id: "j1",
      source: { utm_source: "whatsapp" },
    });
    expect(await screen.findByText("cv.pdf")).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Submit application" });
    expect(submit).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /agree to it being used/ }));
    await userEvent.click(submit);
    expect(await screen.findByText(/MHRS-ACME-2026-000007/)).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/submit/"));
    const headers = new Headers((call![1] as RequestInit).headers);
    expect(headers.get("Idempotency-Key")).toBeTruthy();
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({
      accept_privacy: true,
      objects_to_automated_processing: false,
    });
    expect(screen.getByRole("link", { name: "Track your application" })).toHaveAttribute(
      "href",
      "/candidate/applications/a1",
    );
  });

  it("lists what blocks submission with links back to the step", async () => {
    routes(
      ...base,
      (u, i) =>
        u === "/api/v1/applications/" && i?.method === "POST"
          ? { status: 201, body: app() }
          : undefined,
      (u) =>
        u === "/api/v1/applications/a1/review/"
          ? {
              body: review({
                ready: false,
                missing: [{ step: "documents", code: "document_required", key: "cv" }],
              }),
            }
          : undefined,
    );
    wrap(<ApplyWizard jobId="j1" />);
    expect(await screen.findByText("Attach your CV")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Go to this step" }));
    expect(await screen.findByText("Step 3 of 5 — Documents")).toBeInTheDocument();
  });

  it("EC-APP-14: shows a deadline message when submission is too late", async () => {
    routes(
      ...base,
      (u, i) =>
        u === "/api/v1/applications/" && i?.method === "POST"
          ? { status: 201, body: app() }
          : undefined,
      (u) => (u === "/api/v1/applications/a1/review/" ? { body: review() } : undefined),
      (u) =>
        u.endsWith("/submit/")
          ? {
              status: 422,
              body: {
                error: { code: "deadline_passed", message: "late", details: {}, request_id: "r" },
              },
            }
          : undefined,
    );
    wrap(<ApplyWizard jobId="j1" />);
    await userEvent.click(await screen.findByRole("checkbox", { name: /agree to it being used/ }));
    await userEvent.click(screen.getByRole("button", { name: "Submit application" }));
    expect(await screen.findByText("The closing date has passed")).toBeInTheDocument();
  });

  it("points to the existing application on a duplicate", async () => {
    routes(...base, (u, i) =>
      u === "/api/v1/applications/" && i?.method === "POST"
        ? {
            status: 409,
            body: {
              error: {
                code: "conflict.duplicate_application",
                message: "dup",
                details: { application_id: "a9" },
                request_id: "r",
              },
            },
          }
        : undefined,
    );
    wrap(<ApplyWizard jobId="j1" />);
    expect(await screen.findByRole("link", { name: "Open your application" })).toHaveAttribute(
      "href",
      "/candidate/applications/a9",
    );
  });

  it("EC-APP-20: autosaves answers once after typing stops (debounced, small payload)", async () => {
    routes(
      ...base,
      (u, i) =>
        u === "/api/v1/applications/" && i?.method === "POST"
          ? { status: 201, body: app({ last_step: 4 }) }
          : undefined,
      (u) =>
        u === "/api/v1/applications/a1/review/" ? { body: review({ answers: {} }) } : undefined,
      (u, i) =>
        u === "/api/v1/applications/a1/answers/" && i?.method === "PUT"
          ? { body: review() }
          : undefined,
    );
    wrap(<ApplyWizard jobId="j1" />);
    await userEvent.click(await screen.findByRole("radio", { name: "Yes" }));
    await userEvent.type(await screen.findByLabelText("Which degree?"), "BSc Computing");
    await waitFor(
      () => expect(screen.getByRole("status").textContent).toContain("All changes saved"),
      { timeout: 3000 },
    );
    const puts = fetchMock.mock.calls.filter(
      ([u, i]) => String(u).endsWith("/answers/") && (i as RequestInit)?.method === "PUT",
    );
    expect(puts.length).toBeLessThanOrEqual(2); // not one request per keystroke
    expect(JSON.parse(String((puts.at(-1)![1] as RequestInit).body))).toEqual({
      answers: [
        { key: "has_degree", value: "yes" },
        { key: "degree_name", value: "BSc Computing" },
      ],
    });
  });

  it("reveals a conditional question when the answer matches", async () => {
    routes(
      ...base,
      (u, i) =>
        u === "/api/v1/applications/" && i?.method === "POST"
          ? { status: 201, body: app({ last_step: 4 }) }
          : undefined,
      (u) =>
        u === "/api/v1/applications/a1/review/" ? { body: review({ answers: {} }) } : undefined,
      (u, i) =>
        u === "/api/v1/applications/a1/answers/" && i?.method === "PUT"
          ? { body: review() }
          : undefined,
    );
    wrap(<ApplyWizard jobId="j1" />);
    expect(await screen.findByText("Do you have a degree?")).toBeInTheDocument();
    expect(screen.queryByText("Which degree?")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Yes" }));
    expect(await screen.findByLabelText("Which degree?")).toBeInTheDocument();
  });

  it("EC-APP-06: sends a signed-out candidate to sign in and back to the wizard", async () => {
    routes(
      ...base,
      (u, i) =>
        u === "/api/v1/applications/" && i?.method === "POST"
          ? { status: 201, body: app() }
          : undefined,
      (u) => (u === "/api/v1/applications/a1/review/" ? { body: review() } : undefined),
      (u) =>
        u.endsWith("/submit/")
          ? {
              status: 401,
              body: {
                error: { code: "not_authenticated", message: "x", details: {}, request_id: "r" },
              },
            }
          : undefined,
    );
    wrap(<ApplyWizard jobId="j1" />);
    await userEvent.click(await screen.findByRole("checkbox", { name: /agree to it being used/ }));
    await userEvent.click(screen.getByRole("button", { name: "Submit application" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/login?next=/apply/j1"));
  });
});
