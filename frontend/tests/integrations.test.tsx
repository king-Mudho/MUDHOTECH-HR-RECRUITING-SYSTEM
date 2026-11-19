import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  IntegrationsSettings,
  MessagingPreferences,
  SsoButtons,
} from "@/features/integrations/components";
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

describe("integrations settings", () => {
  it("connects a personal calendar in sandbox mode; admins also see webhooks and API keys", async () => {
    const posts: [string, unknown][] = [];
    const providers = [
      {
        key: "google_calendar",
        name: "Google Calendar",
        kind: "calendar",
        per_user: true,
        credential_fields: ["refresh_token"],
        config_fields: [],
        docs: "",
      },
    ];
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("org_admin") } : undefined),
      (u, init) => {
        if (u === "/api/v1/hr/integrations/" && init?.method === "POST") {
          posts.push([u, JSON.parse(String(init.body))]);
          return { status: 201, body: {} };
        }
        if (u === "/api/v1/hr/integrations/")
          return { body: { providers, connections: [], sandbox_default: true } };
        if (u === "/api/v1/hr/webhooks/")
          return { body: { events: ["job.published"], endpoints: [], deliveries: [] } };
        if (u === "/api/v1/hr/api-keys/") return { body: [] };
        return undefined;
      },
    );
    wrap(<IntegrationsSettings />);
    expect(await screen.findByText(/Sandbox mode/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Refresh token"), "1//token-value");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() =>
      expect(posts[0]![1]).toEqual({
        provider: "google_calendar",
        credentials: { refresh_token: "1//token-value" },
        config: {},
        sandbox: true,
      }),
    );
    expect(await screen.findByRole("heading", { name: "Webhooks" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "API keys" })).toBeInTheDocument();
  });

  it("candidates opt in to SMS", async () => {
    const puts: unknown[] = [];
    routes((u, init) => {
      if (u !== "/api/v1/candidate/messaging-preferences/") return undefined;
      if (init?.method === "PUT") {
        puts.push(JSON.parse(String(init.body)));
        return { body: { sms: true, whatsapp: false } };
      }
      return { body: { sms: false, whatsapp: false } };
    });
    wrap(<MessagingPreferences />);
    await userEvent.click(await screen.findByLabelText("SMS"));
    await waitFor(() => expect(puts).toEqual([{ sms: true, whatsapp: false }]));
  });

  it("shows SSO buttons only when enabled for the deployment", async () => {
    routes((u) =>
      u.endsWith("/config")
        ? { body: { data: { socialaccount: { providers: [{ id: "google", name: "Google" }] } } } }
        : undefined,
    );
    const { unmount } = wrap(<SsoButtons />);
    expect(screen.queryByRole("button", { name: "Continue with Google" })).toBeNull();
    unmount();
    vi.stubEnv("NEXT_PUBLIC_SSO_ENABLED", "true");
    wrap(<SsoButtons />);
    expect(await screen.findByRole("button", { name: "Continue with Google" })).toBeInTheDocument();
    vi.unstubAllEnvs();
  });
});
