import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DeclareConflict } from "@/features/hr-applications/declare-conflict";
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

describe("DeclareConflict", () => {
  it("requires a reason, records it and leaves the application", async () => {
    const posts: unknown[] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("recruiter") } : undefined),
      (u, init) => {
        if (u === "/api/v1/hr/applications/a1/declare-conflict/" && init?.method === "POST") {
          posts.push(JSON.parse(String(init.body)));
          return {
            status: 201,
            body: { application_id: "a1", declared_at: "2026-11-16T10:00:00Z" },
          };
        }
        return undefined;
      },
    );
    wrap(<DeclareConflict applicationId="a1" jobId="j1" />);
    await userEvent.click(screen.getByRole("button", { name: "Declare a conflict of interest" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Declare conflict" });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByRole("textbox"), "My cousin");
    await userEvent.click(confirm);
    await waitFor(() => expect(posts).toEqual([{ reason: "My cousin" }]));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/hr/jobs/j1/applications"));
  });
});
