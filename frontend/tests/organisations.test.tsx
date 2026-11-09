import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CreateOrganisation } from "@/features/organisations/components/create-organisation";
import { InvitationAccept } from "@/features/organisations/components/invitation-accept";
import { PolicySettings, TeamSettings } from "@/features/organisations/components/settings";
import { can } from "@/features/organisations/hooks";
import messages from "../messages/en.json";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
  useParams: () => ({ token: "tok123" }),
  usePathname: () => "/hr/settings/team",
  useSearchParams: () => new URLSearchParams(),
}));

const ORG = "11111111-1111-1111-1111-111111111111";

function me(role: string | null) {
  return {
    id: "u1",
    email: "me@example.test",
    platform_role: "none",
    active_organisation_id: role ? ORG : null,
    memberships: role
      ? [
          {
            id: "m0",
            organisation_id: ORG,
            organisation_name: "Acme",
            organisation_slug: "acme",
            organisation_status: "active",
            role,
          },
        ]
      : [],
    mfa: {
      required: false,
      enabled: false,
      grace_deadline: null,
      in_grace: false,
      enforced: false,
    },
  };
}

type Route = (url: string, init?: RequestInit) => unknown | undefined;
const fetchMock = vi.fn();

function routes(...handlers: Route[]) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    for (const h of handlers) {
      const result = h(url, init);
      if (result !== undefined) {
        const { status = 200, body } = result as { status?: number; body: unknown };
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
      <NextIntlClientProvider locale="en" messages={messages}>
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

const member = (id: string, name: string, role: string) => ({
  id,
  organisation_id: ORG,
  user: {
    id: `u-${id}`,
    email: `${id}@example.test`,
    first_name: name,
    last_name: "",
    display_name: name,
  },
  role,
  status: "active",
  joined_at: "2026-11-01T00:00:00Z",
  deactivated_at: null,
  mfa_enabled: role === "org_admin",
});

describe("client role helper (UI hiding only)", () => {
  it("mirrors the backend matrix for hidden controls", () => {
    expect(can("org_admin", "members.manage")).toBe(true);
    expect(can("hr_manager", "members.manage")).toBe(false);
    expect(can("hr_manager", "members.view")).toBe(true);
    expect(can("recruiter", "policy.view")).toBe(false);
    expect(can(null, "org.update")).toBe(false);
  });
});

describe("TeamSettings", () => {
  const listRoutes = (role: string): Route[] => [
    (u) => (u === "/api/v1/me/" ? { body: me(role) } : undefined),
    (u) =>
      u.startsWith(`/api/v1/organisations/${ORG}/members/`)
        ? {
            body: {
              count: 2,
              results: [member("a", "Ada", "org_admin"), member("b", "Bongani", "recruiter")],
            },
          }
        : undefined,
    (u) =>
      u.startsWith(`/api/v1/organisations/${ORG}/invitations/`)
        ? { body: { count: 0, results: [] } }
        : undefined,
  ];

  it("admins can change roles, deactivate and invite", async () => {
    routes(...listRoutes("org_admin"));
    wrap(<TeamSettings />);
    expect(await screen.findByText("Bongani")).toBeInTheDocument();
    expect(screen.getByLabelText("Role for Bongani")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Deactivate" })).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Send invitation" })).toBeInTheDocument();
  });

  it("HR managers see the team read-only", async () => {
    routes(...listRoutes("hr_manager"));
    wrap(<TeamSettings />);
    expect(await screen.findByText("Bongani")).toBeInTheDocument();
    expect(screen.queryByLabelText("Role for Bongani")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send invitation" })).not.toBeInTheDocument();
  });

  it("recruiters get a permission state, not a broken table", async () => {
    routes(...listRoutes("recruiter"));
    wrap(<TeamSettings />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only company admins and HR managers",
    );
  });

  it("deactivation asks for confirmation and shows reassignment count", async () => {
    routes(
      // DELETE handler first: the list route would otherwise match /members/b/ as well.
      (u, init) =>
        u.includes("/members/b/") && init?.method === "DELETE"
          ? {
              body: {
                membership: { ...member("b", "Bongani", "recruiter"), status: "deactivated" },
                sessions_revoked: 1,
                needs_reassignment: [],
              },
            }
          : undefined,
      ...listRoutes("org_admin"),
    );
    wrap(<TeamSettings />);
    await screen.findByText("Bongani");
    await userEvent.click(screen.getAllByRole("button", { name: "Deactivate" })[1]);
    expect(await screen.findByRole("heading", { name: "Deactivate Bongani?" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Reason/), "Left the company");
    const dialogButtons = screen.getAllByRole("button", { name: "Deactivate" });
    await userEvent.click(dialogButtons[dialogButtons.length - 1]);
    expect(await screen.findByText(/No work needs reassigning/)).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(
      ([u, i]) => String(u).includes("/members/b/") && i?.method === "DELETE",
    );
    expect(JSON.parse(call![1].body)).toEqual({ reason: "Left the company" });
  });
});

describe("PolicySettings", () => {
  const policy = {
    version: 3,
    privacy_notice: "",
    retention_months: 12,
    duplicate_policy: "one_active",
    shortlist_dual_control: false,
    rubric_dual_control: false,
    ai_enabled: true,
    llm_enabled: false,
    blind_review_default: true,
    notification_delay_minutes: 15,
    hide_ai_from_panelists: true,
    rights_request_sla_days: 30,
  };

  it("sends lock_version and explains a stale-version conflict", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("org_admin") } : undefined),
      (u, init) =>
        u === `/api/v1/organisations/${ORG}/policies/` && init?.method === "PATCH"
          ? {
              status: 409,
              body: {
                error: {
                  code: "conflict.stale_version",
                  message: "Changed",
                  details: { current_version: 4 },
                  request_id: "r1",
                },
              },
            }
          : undefined,
      (u) => (u === `/api/v1/organisations/${ORG}/policies/` ? { body: policy } : undefined),
    );
    wrap(<PolicySettings />);
    await userEvent.click(await screen.findByRole("button", { name: "Save policies" }));
    expect(await screen.findByText(/Someone else changed these policies/)).toBeInTheDocument();
    const patch = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH");
    expect(JSON.parse(patch![1].body).lock_version).toBe(3);
  });

  it("is read-only for HR managers", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me("hr_manager") } : undefined),
      (u) => (u === `/api/v1/organisations/${ORG}/policies/` ? { body: policy } : undefined),
    );
    wrap(<PolicySettings />);
    expect(await screen.findByText("Only company admins can change policies.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save policies" })).not.toBeInTheDocument();
  });
});

describe("InvitationAccept", () => {
  const preview = (status: string) => ({
    organisation_name: "Acme",
    organisation_slug: "acme",
    role: "recruiter",
    email_hint: "ch***@example.test",
    status,
    expires_at: "2026-11-15T00:00:00Z",
  });

  it("asks signed-out invitees to sign in", async () => {
    routes(
      (u) =>
        u === "/api/v1/me/"
          ? {
              status: 403,
              body: {
                error: { code: "not_authenticated", message: "x", details: {}, request_id: null },
              },
            }
          : undefined,
      (u) => (u === "/api/v1/invitations/tok123/" ? { body: preview("pending") } : undefined),
    );
    wrap(<InvitationAccept />);
    expect(await screen.findByRole("heading", { name: "Join Acme" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in to accept" })).toHaveAttribute(
      "href",
      "/login?next=%2Finvitations%2Ftok123",
    );
  });

  it("explains expired invitations", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me(null) } : undefined),
      (u) => (u === "/api/v1/invitations/tok123/" ? { body: preview("expired") } : undefined),
    );
    wrap(<InvitationAccept />);
    expect(await screen.findByText(/This invitation has expired/)).toBeInTheDocument();
  });

  it("accepts and switches to the new organisation", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me(null) } : undefined),
      (u) => (u === "/api/v1/invitations/tok123/" ? { body: preview("pending") } : undefined),
      (u) =>
        u === "/api/v1/invitations/tok123/accept/"
          ? { status: 201, body: member("x", "Me", "recruiter") }
          : undefined,
      (u) =>
        u === "/api/v1/me/active-org/"
          ? { body: { organisation_id: ORG, role: "recruiter" } }
          : undefined,
    );
    wrap(<InvitationAccept />);
    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    expect(await screen.findByRole("heading", { name: "Welcome to Acme" })).toBeInTheDocument();
    const activeOrgCall = fetchMock.mock.calls.find(([u]) => u === "/api/v1/me/active-org/");
    expect(JSON.parse(activeOrgCall![1].body)).toEqual({ organisation_id: ORG });
  });

  it("shows the server's email-mismatch message", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me(null) } : undefined),
      (u) => (u === "/api/v1/invitations/tok123/" ? { body: preview("pending") } : undefined),
      (u) =>
        u === "/api/v1/invitations/tok123/accept/"
          ? {
              status: 403,
              body: {
                error: {
                  code: "invitation_email_mismatch",
                  message: "This invitation was sent to a different email address.",
                  details: {},
                  request_id: "r",
                },
              },
            }
          : undefined,
    );
    wrap(<InvitationAccept />);
    await userEvent.click(await screen.findByRole("button", { name: "Accept invitation" }));
    expect(await screen.findByText(/different email address/)).toBeInTheDocument();
  });
});

describe("CreateOrganisation", () => {
  it("validates, creates, activates the org and goes to settings", async () => {
    routes(
      (u) => (u === "/api/v1/me/" ? { body: me(null) } : undefined),
      (u) =>
        u === "/api/v1/organisations/"
          ? { status: 201, body: { id: ORG, name: "Zim Agro" } }
          : undefined,
      (u) =>
        u === "/api/v1/me/active-org/"
          ? { body: { organisation_id: ORG, role: "org_admin" } }
          : undefined,
    );
    wrap(<CreateOrganisation />);
    await userEvent.click(await screen.findByRole("button", { name: "Create organisation" }));
    expect(await screen.findByText("Please fix the following:")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/^Organisation name/), "Zim Agro (Pvt) Ltd");
    await userEvent.type(screen.getByLabelText(/^Website/), "not a url");
    await userEvent.click(screen.getByRole("button", { name: "Create organisation" }));
    expect((await screen.findAllByText(/full web address/)).length).toBeGreaterThan(0);
    await userEvent.clear(screen.getByLabelText(/^Website/));
    await userEvent.click(screen.getByRole("button", { name: "Create organisation" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/hr/settings/organisation"));
  });

  it("asks signed-out visitors to register first", async () => {
    routes((u) =>
      u === "/api/v1/me/"
        ? {
            status: 401,
            body: {
              error: { code: "not_authenticated", message: "x", details: {}, request_id: null },
            },
          }
        : undefined,
    );
    wrap(<CreateOrganisation />);
    expect(await screen.findByRole("link", { name: "Create account" })).toBeInTheDocument();
  });
});
