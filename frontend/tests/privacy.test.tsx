import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidatePrivacy } from "@/features/privacy/candidate-privacy";
import { HRPrivacy } from "@/features/privacy/hr-privacy";
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

const request = (over: Record<string, unknown> = {}) => ({
  id: "r1",
  reference: "RR-2026-ABC123",
  type: "correction",
  status: "received",
  organisation_id: "o1",
  organisation_name: "Acme",
  details: "Degree year is 2019",
  resolution: "",
  statement: "",
  created_at: "2026-11-16T10:00:00Z",
  verified_at: "2026-11-16T10:05:00Z",
  due_at: "2026-12-16T10:00:00Z",
  completed_at: null,
  export_available: false,
  requester: "cand@example.test",
  handled_by: null,
  overdue: false,
  ...over,
});

describe("CandidatePrivacy", () => {
  it("sends a request to the chosen employer with the password", async () => {
    const posts: unknown[] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) => (u === "/api/v1/privacy/consents/" ? { body: [] } : undefined),
      (u) =>
        u === "/api/v1/privacy/employers/" ? { body: [{ id: "o1", name: "Acme" }] } : undefined,
      (u, init) => {
        if (u === "/api/v1/privacy/requests/" && init?.method === "POST") {
          posts.push(JSON.parse(String(init.body)));
          return { status: 201, body: [request({ status: "verifying" })] };
        }
        return u === "/api/v1/privacy/requests/" ? { body: [] } : undefined;
      },
    );
    wrap(<CandidatePrivacy />);
    await userEvent.selectOptions(await screen.findByLabelText("What would you like?"), "export");
    await userEvent.selectOptions(screen.getByLabelText("Who should handle it?"), "org:o1");
    const send = screen.getByRole("button", { name: "Send request" });
    expect(send).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Your password"), "secret-pass");
    await userEvent.click(send);
    await waitFor(() =>
      expect(posts).toEqual([
        {
          type: "export",
          scope: "organisation",
          organisation_id: "o1",
          details: "",
          password: "secret-pass",
        },
      ]),
    );
    expect(await screen.findByText(/open the confirmation link/)).toBeInTheDocument();
  });
});

describe("HRPrivacy", () => {
  it("declines only with a reason the requester will see", async () => {
    const posts: unknown[] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("org_admin") } : undefined),
      (u) => (u === "/api/v1/hr/legal-holds/" ? { body: [] } : undefined),
      (u, init) => {
        if (u === "/api/v1/hr/privacy/requests/r1/action/" && init?.method === "POST") {
          posts.push(JSON.parse(String(init.body)));
          return { body: request({ status: "declined" }) };
        }
        return u === "/api/v1/hr/privacy/requests/" ? { body: [request()] } : undefined;
      },
    );
    wrap(<HRPrivacy />);
    await userEvent.click(await screen.findByRole("button", { name: "Decline with reason" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Decline with reason" });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByRole("textbox"), "Certificate shows 2018");
    await userEvent.click(confirm);
    await waitFor(() =>
      expect(posts).toEqual([{ action: "decline", resolution: "Certificate shows 2018" }]),
    );
  });

  it("is only for organisation admins", async () => {
    routes((u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined));
    wrap(<HRPrivacy />);
    expect(await screen.findByText(/Only organisation admins/)).toBeInTheDocument();
  });
});
