import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApplicationExtractionView,
  ResumeExtractionView,
} from "@/features/resumes/components/extraction";
import messages from "../messages/en.json";

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

const claim = (
  index: number,
  type: string,
  title: string,
  extra: Record<string, unknown> = {},
) => ({
  index,
  type,
  title,
  subtitle: "",
  dates: "",
  detail: "",
  snippet: `${title} snippet`,
  page: 1,
  excluded: false,
  excluded_reason: "",
  ...extra,
});

const preview = {
  document_id: "d1",
  status: "succeeded",
  error_code: "",
  flags: ["hidden_text"],
  imported_at: null,
  claims: [
    claim(0, "experience", "Software Developer", {
      subtitle: "Granite Labs",
      dates: "2022-10 - present",
    }),
    claim(1, "education", "BSc Honours in Computer Science", { subtitle: "Africa University" }),
    claim(2, "skill", "Python"),
    claim(3, "language", "English"),
    claim(4, "protected", "date of birth", {
      excluded: true,
      excluded_reason: "protected_attribute",
      snippet: "",
    }),
  ],
};

describe("ResumeExtractionView", () => {
  it("groups what was read, explains what is ignored and imports only after confirmation", async () => {
    const posts: unknown[] = [];
    routes((url, init) => {
      if (url.includes("/import-to-profile/") && init?.method === "POST") {
        posts.push(JSON.parse(String(init.body)));
        return {
          body: {
            experiences: 1,
            educations: 1,
            certifications: 0,
            skills: 1,
            languages: 1,
            skipped: 0,
          },
        };
      }
      if (url.includes("/candidate/resumes/d1/extraction/")) return { body: preview };
    });
    wrap(<ResumeExtractionView documentId="d1" allowImport />);
    expect(await screen.findByText("Software Developer")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Work experience" })).toBeInTheDocument();
    expect(screen.getByText("Granite Labs · 2022-10 - present")).toBeInTheDocument();
    expect(screen.getByText(/We noticed your date of birth/)).toBeInTheDocument();
    expect(screen.getByText(/Some text in your CV is hidden/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Add these details to my profile" }));
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "Add 4 items" });
    expect(submit).toBeDisabled();
    await userEvent.click(within(dialog).getByLabelText(/Education: BSc Honours/));
    await userEvent.click(within(dialog).getByLabelText(/I've checked these details/));
    await userEvent.click(within(dialog).getByRole("button", { name: "Add 3 items" }));
    await waitFor(() => expect(posts).toEqual([{ confirm: true, indexes: [0, 2, 3] }]));
  });

  it("shows progress while reading and guidance when the file cannot be read", async () => {
    routes(
      (url) =>
        url.includes("/d2/")
          ? { status: 202, body: { ...preview, status: "pending", claims: [] } }
          : undefined,
      (url) =>
        url.includes("/d3/")
          ? { body: { ...preview, status: "failed", error_code: "encrypted_pdf", claims: [] } }
          : undefined,
    );
    wrap(<ResumeExtractionView documentId="d2" />);
    expect(await screen.findByText(/reading your CV/)).toHaveAttribute("aria-live", "polite");
    wrap(<ResumeExtractionView documentId="d3" />);
    expect(await screen.findByText(/password-protected/)).toBeInTheDocument();
  });
});

describe("ApplicationExtractionView", () => {
  it("lets the candidate send a correction for a claim", async () => {
    const posts: { url: string; body: unknown }[] = [];
    const view = {
      application_id: "a1",
      objected: false,
      runs: [
        {
          document_id: "d1",
          filename: "cv.pdf",
          status: "succeeded",
          error_code: "",
          flags: [],
          claims: [
            {
              ...claim(0, "experience", "Software Developer", { subtitle: "Granite Labs" }),
              id: "c1",
              correctable: true,
              corrections: [],
            },
            {
              ...claim(1, "protected", "gender", { excluded: true, snippet: "" }),
              id: "c2",
              correctable: false,
              corrections: [],
            },
          ],
        },
      ],
    };
    routes((url, init) => {
      if (url.includes("/candidate/claims/c1/corrections/") && init?.method === "POST") {
        posts.push({ url, body: JSON.parse(String(init.body)) });
        return {
          status: 201,
          body: {
            id: "x",
            status: "pending",
            created_at: "2026-11-15T10:00:00Z",
            values: {},
            remove: false,
          },
        };
      }
      if (url.includes("/candidate/applications/a1/extraction/")) return { body: view };
    });
    wrap(<ApplicationExtractionView applicationId="a1" />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Correct “Software Developer”" }),
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send correction" }));
    expect(await within(dialog).findByText(/Tell us what should change/)).toBeInTheDocument();
    expect(posts).toHaveLength(0);
    await userEvent.type(within(dialog).getByLabelText("Job title"), "Senior Software Developer");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send correction" }));
    await waitFor(() =>
      expect(posts[0]?.body).toEqual({
        values: { title: "Senior Software Developer" },
        remove: false,
        note: "",
      }),
    );
    expect(screen.queryByRole("button", { name: /Correct “gender”/ })).not.toBeInTheDocument();
  });

  it("explains when the candidate objected to automated processing", async () => {
    routes((url) =>
      url.includes("/extraction/")
        ? { body: { application_id: "a1", objected: true, runs: [] } }
        : undefined,
    );
    wrap(<ApplicationExtractionView applicationId="a1" />);
    expect(await screen.findByText(/without software assistance/)).toBeInTheDocument();
  });
});
