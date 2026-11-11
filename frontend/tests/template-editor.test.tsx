import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  NotificationTemplateSettings,
  unknownVariables,
} from "@/features/notifications/template-editor";
import messages from "../messages/en.json";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/hr/settings/notifications",
  useSearchParams: () => new URLSearchParams(),
}));

const ORG = "11111111-1111-1111-1111-111111111111";
let role = "hr_manager";
const me = () => ({
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
const template = (over: Record<string, unknown> = {}) => ({
  id: "t1",
  key: "shortlisted",
  channel: "email",
  locale: "en",
  subject: "Good news about {{ job_title }}",
  body_md: "Hello {{ recipient_name }}",
  variables: ["job_title", "recipient_name"],
  version: 1,
  active: true,
  is_default: true,
  description: "Candidate shortlisted (after human approval)",
  allowed_variables: ["application_url", "job_title", "organisation_name", "recipient_name"],
  created_at: "2026-11-01T08:00:00Z",
  ...over,
});

const fetchMock = vi.fn();
beforeEach(() => {
  role = "hr_manager";
  document.cookie = "csrftoken=t";
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    if (url === "/api/v1/me/") return json(me());
    if (url.endsWith("/t1/preview/"))
      return json({
        subject: "Good news about Software Developer",
        text: "Hello Tendai",
        html: "<p>Hello Tendai</p>",
      });
    if (url.endsWith("/t1/history/"))
      return json([
        template(),
        template({
          id: "t0",
          version: 1,
          active: true, // still the active platform default, but overridden by t1
          is_default: true,
          subject: "Old subject",
          body_md: "Old body",
        }),
      ]);
    if (url.endsWith("/revert/") && init?.method === "POST")
      return new Response(null, { status: 204 });
    if (url === "/api/v1/hr/notification-templates/" && init?.method === "POST")
      return json(template({ id: "t2", version: 2, is_default: false }), 201);
    if (url.startsWith("/api/v1/hr/notification-templates/?"))
      return json([
        template(),
        template({
          id: "t9",
          key: "not_selected",
          description: "Respectful outcome message (no scores)",
        }),
      ]);
    return json({ error: { code: "not_found", message: "nf", details: {}, request_id: "r" } }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="en" messages={messages} timeZone="Africa/Harare">
        <NotificationTemplateSettings />
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}
const post = (suffix: string) =>
  fetchMock.mock.calls.find(
    ([u, i]) => String(u).endsWith(suffix) && (i as RequestInit)?.method === "POST",
  );
const bodyOf = (c: unknown[] | undefined) => JSON.parse(String((c![1] as RequestInit).body));

describe("unknownVariables", () => {
  it("lists placeholders that are not allowed", () => {
    expect(unknownVariables("Hi {{ name }} {{score}} {{ name }}", ["name"])).toEqual(["score"]);
    expect(unknownVariables("plain", [])).toEqual([]);
  });
});

describe("NotificationTemplateSettings", () => {
  it("blocks unknown variables, inserts allowed ones and previews the draft", async () => {
    show();
    const body = await screen.findByLabelText("Message (Markdown)");
    fireEvent.change(body, { target: { value: "Your score is {{ score }}" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Not available in this message: score");
    expect(screen.getByRole("button", { name: "Save new version" })).toBeDisabled();
    fireEvent.change(body, { target: { value: "Hi " } });
    await userEvent.click(screen.getByRole("button", { name: "Insert organisation_name" }));
    expect(body).toHaveValue("Hi {{ organisation_name }}");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    await waitFor(() =>
      expect(bodyOf(post("/t1/preview/"))).toEqual({
        subject: "Good news about {{ job_title }}",
        body_md: "Hi {{ organisation_name }}",
      }),
    );
    const frame = await screen.findByTitle("Email preview");
    expect(frame).toHaveAttribute("sandbox", "");
    expect(screen.getByText("Good news about Software Developer")).toBeInTheDocument();
  });

  it("saves a new version and confirms it", async () => {
    show();
    const subject = await screen.findByLabelText("Subject");
    fireEvent.change(subject, { target: { value: "Next steps for {{ job_title }}" } });
    await userEvent.click(screen.getByRole("button", { name: "Save new version" }));
    await waitFor(() =>
      expect(bodyOf(post("/api/v1/hr/notification-templates/"))).toEqual({
        key: "shortlisted",
        channel: "email",
        subject: "Next steps for {{ job_title }}",
        body_md: "Hello {{ recipient_name }}",
      }),
    );
    expect(await screen.findByText("Saved. New messages use this version.")).toBeInTheDocument();
  });

  it("loads an earlier version into the editor", async () => {
    show();
    const history = await screen.findByRole("region", { name: "Version history" });
    const buttons = await within(history).findAllByRole("button", { name: "Load into editor" });
    // only the version actually being sent is marked "in use"
    expect(within(history).getAllByText("in use")).toHaveLength(1);
    await userEvent.click(buttons[1]!);
    expect(screen.getByLabelText("Subject")).toHaveValue("Old subject");
    expect(screen.getByLabelText("Message (Markdown)")).toHaveValue("Old body");
  });

  it("is limited to admins and HR managers", async () => {
    role = "recruiter";
    show();
    expect(await screen.findByText(/Only organisation admins and HR managers/)).toBeInTheDocument();
  });
});
