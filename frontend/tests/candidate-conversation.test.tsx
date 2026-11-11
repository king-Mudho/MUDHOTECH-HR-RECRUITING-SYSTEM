import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CandidateClarifications,
  CandidateMessages,
} from "@/features/candidates/components/conversation";
import { CandidateDashboard } from "@/features/candidates/components/dashboard";
import { NotificationCentre } from "@/features/notifications/centre";
import messages from "../messages/en.json";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ id: "a1" }),
  usePathname: () => "/candidate/applications/a1",
  useSearchParams: () => new URLSearchParams(),
}));

type Handler = (url: string, init?: RequestInit) => { status?: number; body: unknown } | undefined;
const fetchMock = vi.fn();
let handlers: Handler[] = [];
beforeEach(() => {
  handlers = [];
  document.cookie = "csrftoken=t";
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    for (const h of handlers) {
      const r = h(url, init);
      if (r)
        return new Response(JSON.stringify(r.body), {
          status: r.status ?? 200,
          headers: { "Content-Type": "application/json" },
        });
    }
    return new Response(
      JSON.stringify({ error: { code: "not_found", message: "nf", details: {}, request_id: "r" } }),
      { status: 404, headers: { "Content-Type": "application/json" } },
    );
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

const posted = (suffix: string) =>
  fetchMock.mock.calls.find(
    ([u, i]) => String(u).endsWith(suffix) && (i as RequestInit)?.method === "POST",
  );
const bodyOf = (call: unknown[] | undefined) => JSON.parse(String((call![1] as RequestInit).body));

const openRequest = {
  id: "c1",
  status: "open",
  message: "Two quick questions.",
  questions: [
    { id: "q1", prompt: "Which year did you finish your BSc?", allow_upload: false },
    { id: "q2", prompt: "Please upload the certificate.", allow_upload: true },
  ],
  answers: [],
  due_at: "2026-11-20T10:00:00Z",
  answered_at: null,
  created_at: "2026-11-11T10:00:00Z",
};

describe("Candidate clarifications", () => {
  it("answers every question and sends them together", async () => {
    handlers = [
      (u, i) =>
        u.endsWith("/clarifications/c1/answer/") && i?.method === "POST"
          ? { body: { ...openRequest, status: "answered" } }
          : undefined,
      (u) => (u.endsWith("/a1/clarifications/") ? { body: [openRequest] } : undefined),
    ];
    wrap(<CandidateClarifications applicationId="a1" />);
    expect(await screen.findByText("Two quick questions.")).toBeInTheDocument();
    const send = screen.getByRole("button", { name: "Send my answers" });
    await userEvent.type(screen.getByLabelText("Your answer to question 1"), "2021");
    expect(send).toBeDisabled(); // question 2 still empty
    expect(screen.getByLabelText(/Add a file/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Your answer to question 2"), "Will post a copy");
    await userEvent.click(send);
    await waitFor(() =>
      expect(bodyOf(posted("/clarifications/c1/answer/"))).toEqual({
        answers: [
          { id: "q1", text: "2021", document_id: null },
          { id: "q2", text: "Will post a copy", document_id: null },
        ],
      }),
    );
  });

  it("shows nothing when there are no requests", async () => {
    handlers = [(u) => (u.endsWith("/a1/clarifications/") ? { body: [] } : undefined)];
    const { container } = wrap(<CandidateClarifications applicationId="a1" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container.querySelector("#clarifications")).toBeNull();
  });
});

describe("Candidate messages", () => {
  it("lists the thread and sends a message", async () => {
    handlers = [
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
                  sender_role: "staff",
                  sender_name: "Acme",
                  mine: false,
                  body: "Can you start in January?",
                  attachment_document_ids: [],
                  created_at: "2026-11-11T10:00:00Z",
                  read_at: null,
                },
              ],
            }
          : undefined,
    ];
    wrap(<CandidateMessages applicationId="a1" canWrite />);
    expect(await screen.findByText("Can you start in January?")).toBeInTheDocument();
    expect(screen.getByText(/Acme/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Write to the employer"), "Yes, from 5 January.");
    await userEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() =>
      expect(bodyOf(posted("/a1/messages/"))).toEqual({
        body: "Yes, from 5 January.",
        attachment_ids: [],
      }),
    );
  });

  it("is read-only for a closed application", async () => {
    handlers = [(u) => (u.endsWith("/a1/messages/") ? { body: [] } : undefined)];
    wrap(<CandidateMessages applicationId="a1" canWrite={false} />);
    expect(await screen.findByText(/new messages can't be sent/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send message" })).not.toBeInTheDocument();
  });
});

describe("Candidate dashboard actions", () => {
  it("lists clarifications, re-uploads and unread messages with links", async () => {
    handlers = [
      (u) =>
        u === "/api/v1/candidate/actions/"
          ? {
              body: [
                {
                  kind: "clarification",
                  application_id: "a1",
                  job_title: "Developer",
                  organisation_name: "Acme",
                  due_at: "2026-11-20T10:00:00Z",
                },
                {
                  kind: "reupload",
                  application_id: "a1",
                  job_title: "Developer",
                  organisation_name: "Acme",
                  document_name: "cv.pdf",
                },
                {
                  kind: "message",
                  application_id: "a1",
                  job_title: "Developer",
                  organisation_name: "Acme",
                  count: 2,
                },
              ],
            }
          : undefined,
      (u) => (u === "/api/v1/applications/" ? { body: [] } : undefined),
      (u) =>
        u === "/api/v1/candidate/profile/"
          ? { body: { profile_completeness: 90, missing: [] } }
          : undefined,
      (u) => (u.startsWith("/api/v1/candidate/profile/skills/") ? { body: [] } : undefined),
    ];
    wrap(<CandidateDashboard />);
    expect(
      await screen.findByText(/Acme asked you a question about Developer/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Answer" })).toHaveAttribute(
      "href",
      "/candidate/applications/a1#clarifications",
    );
    expect(screen.getByText("Please upload cv.pdf again for Developer.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload again" })).toHaveAttribute(
      "href",
      "/candidate/documents",
    );
    expect(screen.getByText("2 new messages from Acme about Developer.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Read" })).toHaveAttribute(
      "href",
      "/candidate/applications/a1#messages",
    );
  });
});

describe("Notification centre", () => {
  it("filters unread, marks read and pages", async () => {
    const item = (id: string, read: boolean) => ({
      id,
      key: "shortlisted",
      text: `Notification ${id}`,
      link: "/candidate/applications/a1",
      organisation: null,
      created_at: "2026-11-11T10:00:00Z",
      read_at: read ? "2026-11-11T11:00:00Z" : null,
    });
    handlers = [
      (u, i) =>
        u.endsWith("/notifications/n1/read/") && i?.method === "POST"
          ? { body: item("n1", true) }
          : undefined,
      (u) =>
        u.startsWith("/api/v1/notifications/?") && u.includes("unread=1")
          ? { body: { count: 1, results: [item("n1", false)] } }
          : undefined,
      (u) =>
        u.startsWith("/api/v1/notifications/?")
          ? { body: { count: 45, results: [item("n1", false), item("n2", true)] } }
          : undefined,
    ];
    wrap(<NotificationCentre />);
    expect(await screen.findByText("Notification n2")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Unread" }));
    await waitFor(() => expect(screen.queryByText("Notification n2")).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Mark as read" }));
    await waitFor(() => expect(posted("/notifications/n1/read/")).toBeTruthy());
  });
});
