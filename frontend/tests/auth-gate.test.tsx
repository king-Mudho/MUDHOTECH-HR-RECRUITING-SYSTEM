import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGate } from "@/features/auth/components/auth-gate";
import messages from "../messages/en.json";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/candidate/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

const fetchMock = vi.fn();
const me = (problem: boolean) => ({
  id: "u1",
  email: "tendai@example.test",
  email_verified: true,
  platform_role: "none",
  active_organisation_id: null,
  memberships: [],
  candidate_profile_id: "p1",
  email_delivery_problem: problem,
  mfa: { required: false, enabled: false, grace_deadline: null, in_grace: false, enforced: false },
});

function show(problem: boolean) {
  fetchMock.mockImplementation(
    async () =>
      new Response(JSON.stringify(me(problem)), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="en" messages={messages} timeZone="Africa/Harare">
        <AuthGate area="candidate">
          <p>Inside</p>
        </AuthGate>
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("AuthGate email delivery banner (EC-NOT-01)", () => {
  it("asks the person to update an address that bounced", async () => {
    show(true);
    expect(await screen.findByText("Inside")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "We couldn't deliver email to tendai@example.test",
    );
    expect(screen.getByRole("link", { name: "update your email address" })).toHaveAttribute(
      "href",
      "/account/security",
    );
  });

  it("shows nothing when delivery is fine", async () => {
    show(false);
    expect(await screen.findByText("Inside")).toBeInTheDocument();
    expect(screen.queryByText(/couldn't deliver email/)).not.toBeInTheDocument();
  });
});
