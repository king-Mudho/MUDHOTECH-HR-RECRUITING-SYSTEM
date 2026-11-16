import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RevealIdentity } from "@/features/hr-applications/reveal-identity";
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

describe("RevealIdentity", () => {
  it("needs a reason, then posts it", async () => {
    const posts: unknown[] = [];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u, init) => {
        if (u === "/api/v1/hr/applications/a1/reveal-identity/" && init?.method === "POST") {
          posts.push(JSON.parse(String(init.body)));
          return {
            status: 201,
            body: { application_id: "a1", revealed_at: "2026-11-16T10:00:00Z" },
          };
        }
        return undefined;
      },
    );
    wrap(<RevealIdentity applicationId="a1" />);
    expect(screen.getByText(/name and contact details are hidden/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reveal identity" }));
    const confirm = screen.getByRole("button", { name: "Reveal" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/why do you need/i), "Reference check");
    await userEvent.click(confirm);
    await waitFor(() => expect(posts).toEqual([{ reason: "Reference check" }]));
  });
});
