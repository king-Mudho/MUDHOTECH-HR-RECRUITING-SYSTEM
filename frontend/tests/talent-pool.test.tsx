import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { parseTags, TalentPoolRoute, talentQuery } from "@/features/talentpool/components";
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

const candidate = {
  id: "e1",
  name: "Tatenda Synthetic",
  headline: "Python developer",
  city: "Harare",
  skills: ["Python", "Django"],
  qualifications: ["BSc Computer Science"],
  latest_title: "Developer",
  tags: [],
  joined_at: "2026-11-01T10:00:00Z",
  expires_at: "2027-11-01T10:00:00Z",
  latest_application: { id: "a1", reference: "MHR-2026-0001", job_title: "Developer" },
  invited_job_ids: [],
};

describe("talent pool helpers", () => {
  it("builds the query and parses tags", () => {
    expect(talentQuery({ q: " python ", skill: "Python, SQL ,", tag: "" })).toEqual({
      q: "python",
      skill: ["Python", "SQL"],
      tag: undefined,
      page_size: "25",
    });
    expect(parseTags("Backend,  backend , Backend , Senior   dev")).toEqual([
      "Backend",
      "backend",
      "Senior dev",
    ]);
  });
});

describe("TalentPoolRoute", () => {
  it("searches consented members and sends an invitation", async () => {
    const calls: string[] = [];
    const posts: unknown[] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined),
      (u) =>
        u.startsWith("/api/v1/hr/jobs/")
          ? {
              body: {
                count: 1,
                next: null,
                previous: null,
                results: [{ id: "j2", title: "Data Engineer" }],
              },
            }
          : undefined,
      (u, init) => {
        if (u.includes("/invite/") && init?.method === "POST") {
          posts.push(JSON.parse(String(init.body)));
          return { status: 201, body: { id: "i1", job_id: "j2", invited_at: "2026-11-19" } };
        }
        if (!u.startsWith("/api/v1/hr/talent-pool/")) return undefined;
        calls.push(u);
        return { body: { count: 1, next: null, previous: null, results: [candidate] } };
      },
    );
    wrap(<TalentPoolRoute />);
    expect(await screen.findByRole("heading", { name: "Tatenda Synthetic" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Skills"), "Python, SQL");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(calls.some((u) => u.includes("skill=Python") && u.includes("skill=SQL"))).toBe(true),
    );
    await userEvent.selectOptions(await screen.findByLabelText("Invite to apply for"), "j2");
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText("Invitation sent.")).toBeInTheDocument();
    expect(posts).toEqual([{ job_id: "j2" }]);
  });

  it("is forbidden for hiring managers", async () => {
    routes((u) => (u === "/api/v1/me/" ? { body: me("hiring_manager") } : undefined));
    wrap(<TalentPoolRoute />);
    expect(
      await screen.findByText("You don't have access to the talent pool in this organisation."),
    ).toBeInTheDocument();
  });
});
