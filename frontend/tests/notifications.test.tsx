import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NotificationBell, POLL_MS } from "@/features/notifications/bell";
import messages from "../messages/en.json";

const fetchMock = vi.fn();
let unread = 120;
const items = [
  {
    id: "n1",
    key: "shortlisted",
    text: "Acme moved your application for Developer to the next stage.",
    link: "/candidate/applications/7",
    organisation: null,
    created_at: "2026-11-10T08:00:00Z",
    read_at: null,
  },
  {
    id: "n2",
    key: "recruitment_paused",
    text: "Recruitment for Developer is paused; your application is kept.",
    link: "",
    organisation: null,
    created_at: "2026-11-09T08:00:00Z",
    read_at: "2026-11-09T09:00:00Z",
  },
];

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  unread = 120;
  document.cookie = "csrftoken=t";
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/unread-count/")) return json({ count: unread });
    if (url.endsWith("/read-all/") && init?.method === "POST") {
      unread = 0;
      return json({ count: 0 });
    }
    if (url.endsWith("/read/") && init?.method === "POST") {
      unread -= 1;
      return json({ ...items[0], read_at: "2026-11-10T09:00:00Z" });
    }
    if (url.startsWith("/api/v1/notifications/")) return json({ count: 2, results: items });
    return new Response("{}", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="en" messages={messages} timeZone="Africa/Harare">
        <NotificationBell />
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}

describe("NotificationBell", () => {
  it("shows the unread count in its accessible name and caps the badge", async () => {
    show();
    const bell = await screen.findByRole("button", { name: "Notifications, 120 unread" });
    expect(bell).toHaveTextContent("99+");
    expect(bell).toHaveAttribute("aria-expanded", "false");
    expect(POLL_MS).toBe(30_000);
  });

  it("opens a panel, marks one item read, marks all read and closes on Escape", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: /Notifications, 120/ }));
    expect(await screen.findByText(/moved your application for Developer/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "/candidate/applications/7",
    );
    expect(screen.getAllByRole("button", { name: "Mark as read" })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Mark as read" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) => String(u).endsWith("/notifications/n1/read/")),
      ).toBe(true),
    );
    await userEvent.click(screen.getByRole("button", { name: "Mark all as read" }));
    expect(await screen.findByRole("button", { name: "Notifications" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Notifications" })).not.toBeInTheDocument();
  });
});
