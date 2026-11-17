import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import axe from "axe-core";

import { AiGovernance } from "@/features/ai-governance/ai-governance";
import messages from "../messages/en.json";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({}),
  usePathname: () => "/admin/model-registry",
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

const state = (enabled: boolean) => ({
  platform_enabled: enabled,
  disabled_organisations: [],
  models: [
    {
      id: "m1",
      kind: "rules",
      name: "mhrs-screening-engine",
      version: "7+3",
      purpose: "Evidence extraction and scoring",
      provider: "MudhoTech Solutions",
      data_policy: "Never used for training.",
      limitations: "Rules coverage.",
      evaluation_report: "docs/reports/",
      active_from: "2026-11-01T00:00:00Z",
      active_to: null,
      active: true,
    },
  ],
});

describe("AiGovernance", () => {
  it("lists the registry and lets a platform admin switch AI off with a reason", async () => {
    const posts: unknown[] = [];
    routes(
      (u) =>
        u === "/api/v1/me/"
          ? { body: { ...me("none"), platform_role: "platform_admin" } }
          : undefined,
      (u, init) => {
        if (u !== "/api/v1/platform/ai/") return undefined;
        if (init?.method === "POST") {
          posts.push(JSON.parse(String(init.body)));
          return { body: state(false) };
        }
        return { body: state(true) };
      },
    );
    wrap(<AiGovernance />);
    expect(await screen.findByText("mhrs-screening-engine@7+3")).toBeInTheDocument();
    expect(screen.getByText(/AI screening is on/)).toBeInTheDocument();
    const button = await screen.findByRole("button", { name: "Switch AI off" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: "Incident 42: drift" } });
    fireEvent.click(button);
    expect(await screen.findByText(/OFF for every organisation/)).toBeInTheDocument();
    expect(posts).toEqual([{ enabled: false, reason: "Incident 42: drift" }]);
  });

  it("is read-only for platform support", async () => {
    routes(
      (u) =>
        u === "/api/v1/me/"
          ? { body: { ...me("none"), platform_role: "platform_support" } }
          : undefined,
      (u) => (u === "/api/v1/platform/ai/" ? { body: state(true) } : undefined),
    );
    wrap(<AiGovernance />);
    expect(await screen.findByText(/Only platform admins/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Switch AI off" })).toBeNull();
  });

  it("has no serious or critical axe violations (jsdom, contrast checked in Playwright)", async () => {
    routes(
      (u) =>
        u === "/api/v1/me/"
          ? { body: { ...me("none"), platform_role: "platform_admin" } }
          : undefined,
      (u) => (u === "/api/v1/platform/ai/" ? { body: state(true) } : undefined),
    );
    const { container } = wrap(<AiGovernance />);
    await screen.findByRole("button", { name: "Switch AI off" });
    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    const serious = results.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact ?? ""),
    );
    expect(serious.map((v) => v.id)).toEqual([]);
  });
});
