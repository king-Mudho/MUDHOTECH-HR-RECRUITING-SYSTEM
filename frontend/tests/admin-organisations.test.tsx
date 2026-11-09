import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminOrganisations } from "@/features/admin/organisations";
import messages from "../messages/en.json";

const ORG = {
  id: "o1",
  name: "Zim Agro (Pvt) Ltd",
  slug: "zim-agro",
  status: "pending_verification",
  industry: "Agriculture",
  city: "Gweru",
  country: "ZW",
  website: "",
  registration_number: "123/2026",
  created_at: "2026-11-01T00:00:00Z",
  verified_at: null,
  verified_by_email: null,
  member_count: 1,
};

const fetchMock = vi.fn();

function setup(platformRole: string) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const ok = (body: unknown) =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    if (url === "/api/v1/me/") return ok({ id: "a", platform_role: platformRole, memberships: [] });
    if (url.startsWith("/api/v1/platform/organisations/o1/") && init?.method === "POST") {
      return ok({ ...ORG, status: url.includes("verify") ? "active" : "suspended" });
    }
    if (url.startsWith("/api/v1/platform/organisations/")) return ok({ count: 1, results: [ORG] });
    return new Response("{}", { status: 404 });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="en" messages={messages}>
        <AdminOrganisations />
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

describe("AdminOrganisations", () => {
  it("lists pending organisations by default and verifies one", async () => {
    setup("platform_admin");
    expect(await screen.findByText("Zim Agro (Pvt) Ltd")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([u]) => String(u).includes("status=pending_verification")),
    ).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(
      await screen.findByRole("heading", { name: "Verify Zim Agro (Pvt) Ltd?" }),
    ).toBeInTheDocument();
    const confirm = screen.getAllByRole("button", { name: "Verify" });
    await userEvent.click(confirm[confirm.length - 1]);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([u, i]) => u === "/api/v1/platform/organisations/o1/verify/" && i?.method === "POST",
        ),
      ).toBe(true),
    );
  });

  it("requires a reason to suspend", async () => {
    setup("platform_admin");
    await userEvent.click(await screen.findByRole("button", { name: "Suspend" }));
    const buttons = screen.getAllByRole("button", { name: "Suspend" });
    const confirm = buttons[buttons.length - 1];
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Reason/), "Fraudulent adverts reported");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([u]) => u === "/api/v1/platform/organisations/o1/suspend/",
      );
      expect(JSON.parse(call![1].body)).toEqual({ reason: "Fraudulent adverts reported" });
    });
  });

  it("platform support sees a read-only list", async () => {
    setup("platform_support");
    expect(await screen.findByText("Zim Agro (Pvt) Ltd")).toBeInTheDocument();
    expect(screen.getByText("Read-only view for platform support.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Verify" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Suspend" })).not.toBeInTheDocument();
  });

  it("filters by status", async () => {
    setup("platform_admin");
    await screen.findByText("Zim Agro (Pvt) Ltd");
    await userEvent.click(screen.getByRole("button", { name: "Suspended" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes("status=suspended"))).toBe(true),
    );
  });
});
