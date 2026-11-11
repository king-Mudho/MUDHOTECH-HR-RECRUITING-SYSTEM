import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ClarificationsPanel, MessagesPanel, NotesPanel } from "@/features/hr-applications/panels";
import type { HRApplicationDetail } from "@/features/hr-applications/api";
import { PipelineBoard } from "@/features/hr-applications/pipeline";
import messages from "../messages/en.json";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: "j1" }),
  usePathname: () => "/hr/jobs/j1/pipeline",
  useSearchParams: () => new URLSearchParams(),
}));

const ORG = "11111111-1111-1111-1111-111111111111";
let role = "hr_manager";
const me = () => ({
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

const row = (id: string, status: string, name: string) => ({
  id,
  reference: `MHRS-ACME1A2B-2026-00000${id.slice(-1)}`,
  status,
  submitted_at: "2026-11-01T08:00:00Z",
  candidate_name: name,
  candidate_email: `${id}@example.test`,
  channel: "web",
  is_assisted: false,
  objects_to_automated_processing: false,
  tags: id === "a1" ? ["senior"] : [],
  assigned_recruiter: null,
  lock_version: 3,
});

const detail = (status: string, allowed: string[]) => ({
  ...row("a1", status, "Rudo Moyo"),
  withdrawn_at: null,
  withdraw_reason: "",
  job: { id: "j1", title: "Software Developer", version: 1 },
  candidate: {},
  documents: [],
  answers: [],
  timeline: [],
  allowed_transitions: allowed,
});

type Handler = (url: string, init?: RequestInit) => { status?: number; body: unknown } | undefined;
const fetchMock = vi.fn();
let extra: Handler[] = [];
function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
beforeEach(() => {
  role = "hr_manager";
  extra = [];
  document.cookie = "csrftoken=t";
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    for (const h of extra) {
      const r = h(url, init);
      if (r) return json(r.status ?? 200, r.body);
    }
    if (url === "/api/v1/me/") return json(200, me());
    if (url === "/api/v1/hr/jobs/j1/") return json(200, { id: "j1", title: "Software Developer" });
    if (url.startsWith("/api/v1/hr/jobs/j1/applications/"))
      return json(200, {
        count: 2,
        results: [row("a1", "under_review", "Rudo Moyo"), row("a2", "on_hold", "Tendai Chari")],
      });
    if (url === "/api/v1/hr/applications/a1/")
      return json(
        200,
        detail("under_review", [
          "needs_information",
          "not_selected",
          "on_hold",
          "shortlisted",
          "withdrawn",
        ]),
      );
    if (url.startsWith("/api/v1/hr/decision-reasons/"))
      return json(200, [
        {
          code: "essential_not_met",
          label: "Essential requirement not evidenced",
          applies_to: "not_selected",
        },
        { code: "other", label: "Other (explained in the note)", applies_to: "not_selected" },
      ]);
    if (url === "/api/v1/hr/jobs/j1/assignments/")
      return json(200, [
        {
          id: "as1",
          membership: "m1",
          user_id: "u2",
          role_on_job: "recruiter",
          user_name: "Rudo Recruiter",
          org_role: "recruiter",
          created_at: "",
        },
      ]);
    return json(404, { error: { code: "not_found", message: "nf", details: {}, request_id: "r" } });
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

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

function dataTransfer() {
  const store: Record<string, string> = {};
  return {
    setData: (k: string, v: string) => {
      store[k] = v;
    },
    getData: (k: string) => store[k] ?? "",
    get types() {
      return Object.keys(store);
    },
    effectAllowed: "",
  };
}

const body = (call: unknown[]) => JSON.parse(String((call[1] as RequestInit).body));

describe("PipelineBoard", () => {
  it("shows columns and cards, and a drag asks for a reason before the server change", async () => {
    extra = [
      (u, i) =>
        u.endsWith("/a1/transition/") && i?.method === "POST"
          ? { body: detail("not_selected", ["under_review"]) }
          : undefined,
    ];
    wrap(<PipelineBoard jobId="j1" />);
    const card = (await screen.findByRole("link", { name: "Rudo Moyo" })).closest("li")!;
    expect(within(card).getByText("senior")).toBeInTheDocument();
    const target = document.querySelector('[data-status="not_selected"]')!;
    const dt = dataTransfer();
    fireEvent.dragStart(card, { dataTransfer: dt });
    fireEvent.dragOver(target, { dataTransfer: dt });
    fireEvent.drop(target, { dataTransfer: dt });
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("New status")).toHaveValue("not_selected");
    const confirm = within(dialog).getByRole("button", { name: "Change status" });
    expect(confirm).toBeDisabled(); // reason required
    await within(dialog).findByRole("option", { name: "Essential requirement not evidenced" });
    await userEvent.selectOptions(
      await within(dialog).findByLabelText(/Reason/),
      "essential_not_met",
    );
    expect(within(dialog).getByText(/notification delay/)).toBeInTheDocument();
    await userEvent.click(confirm);
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/a1/transition/"));
      expect(body(call!)).toEqual({
        to_status: "not_selected",
        reason_code: "essential_not_met",
        reason_text: "",
        lock_version: 3,
      });
    });
  });

  it("explains an illegal drag instead of sending it", async () => {
    wrap(<PipelineBoard jobId="j1" />);
    const card = (await screen.findByRole("link", { name: "Rudo Moyo" })).closest("li")!;
    const target = document.querySelector('[data-status="submitted"]')!;
    const dt = dataTransfer();
    fireEvent.dragStart(card, { dataTransfer: dt });
    fireEvent.drop(target, { dataTransfer: dt });
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "An application can't move from Under review to Submitted.",
    );
    expect(within(dialog).getByRole("button", { name: "Change status" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/transition/"))).toBe(false);
  });

  it("can be used with the keyboard and shows server rejections", async () => {
    extra = [
      (u, i) =>
        u.endsWith("/a1/transition/") && i?.method === "POST"
          ? {
              status: 409,
              body: {
                error: {
                  code: "conflict.invalid_transition",
                  message: "no",
                  details: { allowed: ["on_hold"] },
                  request_id: "r",
                },
              },
            }
          : undefined,
    ];
    wrap(<PipelineBoard jobId="j1" />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Move Rudo Moyo to another stage" }),
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.selectOptions(
      await within(dialog).findByLabelText("New status"),
      "needs_information",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Change status" }));
    expect(
      await within(dialog).findByText(/From here it can move to: On hold/),
    ).toBeInTheDocument();
  });
});

const app = detail("under_review", []) as unknown as HRApplicationDetail;

describe("Application panels", () => {
  it("adds a note that mentions a colleague", async () => {
    extra = [
      (u, i) =>
        u.endsWith("/a1/notes/") && i?.method === "POST"
          ? {
              status: 201,
              body: {
                id: "n1",
                body: "Looks strong",
                visibility: "team",
                mentions: ["u2"],
                author_name: "Me",
                mine: true,
                created_at: "2026-11-01T08:00:00Z",
              },
            }
          : undefined,
      (u) => (u.endsWith("/a1/notes/") ? { body: [] } : undefined),
    ];
    wrap(<NotesPanel app={app} />);
    await userEvent.type(await screen.findByLabelText("Add a note"), "Looks strong");
    await userEvent.click(await screen.findByRole("checkbox", { name: "Rudo Recruiter" }));
    await userEvent.click(screen.getByRole("button", { name: "Save note" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([u, i]) => String(u).endsWith("/notes/") && (i as RequestInit)?.method === "POST",
      );
      expect(body(call!)).toEqual({ body: "Looks strong", mentions: ["u2"], visibility: "team" });
    });
  });

  it("composes a clarification from a template", async () => {
    extra = [
      (u, i) =>
        u.endsWith("/a1/clarifications/") && i?.method === "POST"
          ? { status: 201, body: { id: "c1" } }
          : undefined,
      (u) => (u.endsWith("/a1/clarifications/") ? { body: [] } : undefined),
      (u) =>
        u === "/api/v1/hr/clarification-templates/"
          ? {
              body: [{ key: "availability", prompt: "When could you start?", allow_upload: false }],
            }
          : undefined,
    ];
    wrap(<ClarificationsPanel app={app} />);
    await screen.findByRole("option", { name: "When could you start?" });
    await userEvent.selectOptions(
      await screen.findByLabelText("Start from a common question"),
      "availability",
    );
    expect(screen.getByLabelText("Question 1")).toHaveValue("When could you start?");
    await userEvent.click(screen.getByRole("button", { name: "Send request" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([u, i]) => String(u).endsWith("/clarifications/") && (i as RequestInit)?.method === "POST",
      );
      const sent = body(call!);
      expect(sent.questions).toEqual([{ prompt: "When could you start?", allow_upload: false }]);
      expect(new Date(sent.due_at).getTime()).toBeGreaterThan(Date.now() + 2 * 86_400_000);
    });
  });

  it("shows the conversation and sends a message", async () => {
    extra = [
      (u, i) =>
        u.endsWith("/a1/messages/") && i?.method === "POST"
          ? { status: 201, body: { id: "m2" } }
          : undefined,
      (u) =>
        u.endsWith("/a1/messages/")
          ? {
              body: [
                {
                  id: "m1",
                  sender_role: "candidate",
                  sender_name: "Rudo Moyo",
                  mine: false,
                  body: "Is it remote?",
                  attachment_document_ids: [],
                  created_at: "2026-11-01T08:00:00Z",
                  read_at: null,
                },
              ],
            }
          : undefined,
    ];
    wrap(<MessagesPanel app={app} />);
    expect(await screen.findByText("Is it remote?")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Write to the candidate"), "Hybrid, 3 days.");
    await userEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([u, i]) => String(u).endsWith("/messages/") && (i as RequestInit)?.method === "POST",
      );
      expect(body(call!)).toEqual({ body: "Hybrid, 3 days.", attachment_ids: [] });
    });
  });
});
