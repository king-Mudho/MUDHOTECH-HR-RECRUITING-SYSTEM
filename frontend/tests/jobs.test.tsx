import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JobOverview } from "@/features/jobs/components/job-overview";
import { JobsTable } from "@/features/jobs/components/jobs-table";
import { JobWizard } from "@/features/jobs/components/wizard";
import { toPayload } from "@/features/jobs/components/step-details";
import { canJob } from "@/features/jobs/hooks";
import {
  criterionSchema,
  detailsFromJob,
  emptyCriterion,
  emptyQuestion,
  questionsToInput,
  rubricProblems,
  rubricTotal,
  slugKey,
} from "@/features/jobs/schemas";
import { utcIsoToZonedLocal, zonedLocalToUtcIso } from "@/lib/timezone";
import messages from "../messages/en.json";

let search = new URLSearchParams();
const push = vi.fn();
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace, refresh: vi.fn() }),
  useParams: () => ({ id: JOB }),
  usePathname: () => `/hr/jobs/${JOB}/edit`,
  useSearchParams: () => search,
}));

const ORG = "11111111-1111-1111-1111-111111111111";
const JOB = "22222222-2222-2222-2222-222222222222";

function me(role: string) {
  return {
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
    mfa: {
      required: false,
      enabled: false,
      grace_deadline: null,
      in_grace: false,
      enforced: false,
    },
  };
}

const bands = [
  { score: 0, descriptor: "No evidence" },
  { score: 50, descriptor: "Some" },
  { score: 100, descriptor: "Strong" },
];

function job(overrides: Record<string, unknown> = {}) {
  return {
    id: JOB,
    slug: "software-developer-acme",
    title: "Software Developer",
    reference_code: "",
    status: "draft",
    visibility: "public",
    department: null,
    locations: [],
    workplace_type: "on_site",
    employment_type: "full_time",
    seniority: "",
    openings: 1,
    closes_at: "2030-03-31T21:59:00Z",
    timezone: "Africa/Harare",
    publish_at: null,
    published_at: null,
    closed_at: null,
    current_version: {
      id: "v1",
      number: 1,
      status: "draft",
      change_note: "",
      submitted_at: null,
      approved_at: null,
      created_at: "",
    },
    lock_version: 3,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-08T00:00:00Z",
    salary_min: null,
    salary_max: null,
    salary_currency: "USD",
    salary_period: "month",
    salary_disclosed: false,
    start_date: null,
    close_reason: "",
    published_version_number: null,
    version: {
      id: "v1",
      number: 1,
      status: "draft",
      summary: "Build apps",
      responsibilities_html: "<p>Code</p>",
      requirements_html: "",
      benefits_html: "",
      required_documents: ["cv"],
      change_note: "",
      submitted_by: null,
      submitted_at: null,
      approved_by: null,
      approved_at: null,
      created_at: "",
    },
    criteria: [],
    rubric: {
      total_weight: 100,
      status: "draft",
      categories: [
        { key: "technical", label: "Technical skills", weight: 35, bands },
        { key: "experience", label: "Relevant experience", weight: 25, bands },
        { key: "competency", label: "Job competencies", weight: 20, bands },
        { key: "qualification", label: "Qualifications", weight: 10, bands },
        { key: "answers", label: "Screening answers", weight: 10, bands },
      ],
    },
    questions: [],
    ...overrides,
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
      {
        status: 404,
      },
    );
  });
}
const meRoute =
  (role: string): Route =>
  (u) =>
    u === "/api/v1/me/" ? { body: me(role) } : undefined;
const readiness: Route = (u) =>
  u.includes("/lint/")
    ? {
        body: {
          ready: false,
          stage: "submit",
          checks: [{ id: "deadline", ok: false, message: "x", blocking: true, details: {} }],
          warnings: [],
        },
      }
    : undefined;

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
  push.mockReset();
  replace.mockReset();
  search = new URLSearchParams();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("timezone helpers (EC-JOB-05)", () => {
  it("converts vacancy wall-clock time to UTC and back", () => {
    expect(zonedLocalToUtcIso("2030-03-31T23:59", "Africa/Harare")).toBe(
      "2030-03-31T21:59:00.000Z",
    );
    expect(utcIsoToZonedLocal("2030-03-31T21:59:00Z", "Africa/Harare")).toBe("2030-03-31T23:59");
    expect(zonedLocalToUtcIso("2030-07-01T09:00", "Europe/London")).toBe(
      "2030-07-01T08:00:00.000Z",
    );
    expect(zonedLocalToUtcIso("not a date", "UTC")).toBeNull();
  });
});

describe("job schemas", () => {
  it("requires a justification for essential criteria", () => {
    const c = { ...emptyCriterion(), title: "Python", importance: "essential" as const };
    expect(criterionSchema.safeParse(c).success).toBe(false);
    expect(criterionSchema.safeParse({ ...c, justification: "Core stack" }).success).toBe(true);
    expect(criterionSchema.safeParse({ ...c, importance: "preferred" }).success).toBe(true);
  });

  it("checks rubric totals and bands (EC-JOB-02)", () => {
    const rows = [
      { key: "technical" as const, label: "", weight: 60, bands },
      { key: "experience" as const, label: "", weight: 30, bands },
    ];
    expect(rubricTotal(rows)).toBe(90);
    expect(rubricProblems(rows)).toContain("rubricTotal");
    rows[1]!.weight = 40;
    expect(rubricProblems(rows)).toEqual([]);
    rows[0]!.bands = [{ score: 0, descriptor: "" }];
    expect(rubricProblems(rows)).toContain("rubricBands");
  });

  it("serialises questions with branching, scoring and knock-out", () => {
    const a = {
      ...emptyQuestion(new Set()),
      key: "licence",
      prompt: "Licence?",
      is_knockout: true,
      knockout_expected: "yes",
    };
    const b = {
      ...emptyQuestion(new Set(["licence"])),
      key: "class",
      type: "single_choice" as const,
      prompt: "Class?",
      options: [
        { label: "Class 4", value: "class-4", points: "5" },
        { label: "Class 2", value: "class-2", points: "" },
      ],
      scoring_mode: "options",
      show_if_question: "licence",
      show_if_value: "yes",
    };
    const [qa, qb] = questionsToInput([a, b]);
    expect(qa).toMatchObject({
      key: "licence",
      is_knockout: true,
      knockout_expected: "yes",
      options: [],
    });
    expect(qb!.branching).toEqual({ show_if: { question: "licence", op: "eq", value: "yes" } });
    expect(qb!.options).toEqual([
      { label: "Class 4", value: "class-4", points: "5" },
      { label: "Class 2", value: "class-2", points: null },
    ]);
    expect(slugKey("Do you have a licence?", new Set(["do-you-have-a-licence"]))).toBe(
      "do-you-have-a-licence-2",
    );
  });

  it("maps details to the API payload and keeps live deadlines out", () => {
    const values = detailsFromJob(job() as never, (iso, tz) => utcIsoToZonedLocal(iso, tz));
    expect(values.closes_at_local).toBe("2030-03-31T23:59");
    const payload = toPayload({ ...values, salary_min: "" });
    expect(payload.closes_at).toBe("2030-03-31T21:59:00.000Z");
    expect(payload.salary_min).toBeNull();
    expect(toPayload(values, job({ status: "published" }) as never).closes_at).toBeUndefined();
  });

  it("mirrors the backend job permissions for hiding controls", () => {
    expect(canJob("recruiter", "jobs.create")).toBe(true);
    expect(canJob("recruiter", "jobs.approve")).toBe(false);
    expect(canJob("hr_manager", "jobs.publish")).toBe(true);
    expect(canJob("panelist", "jobs.view")).toBe(false);
    expect(canJob("auditor", "jobs.create")).toBe(false);
  });
});

describe("JobsTable", () => {
  it("lists vacancies with status and links", async () => {
    routes(meRoute("recruiter"), (u) =>
      u.startsWith("/api/v1/hr/jobs/")
        ? {
            body: { count: 1, next: null, previous: null, results: [job({ status: "published" })] },
          }
        : undefined,
    );
    wrap(<JobsTable />);
    const link = await screen.findByRole("link", { name: "Software Developer" });
    expect(link).toHaveAttribute("href", `/hr/jobs/${JOB}`);
    expect(screen.getByText("Published")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New vacancy" })).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([u]) => String(u).startsWith("/api/v1/hr/jobs/"));
    expect((call![1] as RequestInit).headers).toBeInstanceOf(Headers);
    expect(((call![1] as RequestInit).headers as Headers).get("X-Org-Id")).toBe(ORG);
  });

  it("shows an empty state and hides create for hiring managers", async () => {
    routes(meRoute("hiring_manager"), (u) =>
      u.startsWith("/api/v1/hr/jobs/")
        ? { body: { count: 0, next: null, previous: null, results: [] } }
        : undefined,
    );
    wrap(<JobsTable />);
    expect(await screen.findByText("No vacancies yet")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New vacancy" })).not.toBeInTheDocument();
  });

  it("panelists get a permission state", async () => {
    routes(meRoute("panelist"));
    wrap(<JobsTable />);
    expect(await screen.findByRole("alert")).toHaveTextContent("don't have access");
  });
});

describe("JobWizard", () => {
  it("rubric step keeps a running total and blocks totals other than 100", async () => {
    search = new URLSearchParams("step=rubric");
    routes(meRoute("recruiter"), readiness, (u) =>
      u === `/api/v1/hr/jobs/${JOB}/` ? { body: job() } : undefined,
    );
    wrap(<JobWizard jobId={JOB} />);
    const total = await screen.findByTestId("rubric-total");
    expect(total).toHaveTextContent("Total: 100%");
    fireEvent.change(screen.getByLabelText("Weight (%)", { selector: "#weight-technical" }), {
      target: { value: "30" },
    });
    expect(total).toHaveTextContent("Total: 95%");
    await userEvent.click(screen.getAllByRole("button", { name: "Save" })[0]!);
    expect(await screen.findByText("Weights must add up to exactly 100.")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([u, i]) => String(u).includes("/rubric/") && (i as RequestInit)?.method === "PUT",
      ),
    ).toBe(false);
  });

  it("shows a conflict prompt when someone else saved first (EC-JOB-07)", async () => {
    search = new URLSearchParams("step=rubric");
    routes(meRoute("recruiter"), readiness, (u, init) => {
      if (u.includes("/rubric/") && init?.method === "PUT") {
        expect(JSON.parse(String(init.body)).lock_version).toBe(3);
        return {
          status: 409,
          body: {
            error: {
              code: "conflict.stale_version",
              message: "Changed",
              details: {},
              request_id: "r1",
            },
          },
        };
      }
      return u === `/api/v1/hr/jobs/${JOB}/` ? { body: job() } : undefined;
    });
    wrap(<JobWizard jobId={JOB} />);
    await screen.findByTestId("rubric-total");
    await userEvent.click(screen.getAllByRole("button", { name: "Save" })[0]!);
    expect(await screen.findByText("Someone else changed this vacancy")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload latest version" })).toBeInTheDocument();
  });

  it("locks editing for approved versions", async () => {
    routes(meRoute("recruiter"), readiness, (u) =>
      u === `/api/v1/hr/jobs/${JOB}/`
        ? { body: job({ status: "approved", version: { ...job().version, status: "approved" } }) }
        : undefined,
    );
    wrap(<JobWizard jobId={JOB} />);
    expect(await screen.findByText("This version is locked")).toBeInTheDocument();
    expect(screen.getByLabelText(/Job title/)).toBeDisabled();
  });

  it("creates a draft from the details step and moves to requirements", async () => {
    routes(meRoute("recruiter"), (u, init) => {
      if (u === "/api/v1/hr/jobs/" && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        expect(body.title).toBe("Accountant");
        return { status: 201, body: job({ title: "Accountant" }) };
      }
      if (u.includes("/departments/") || u.includes("/locations/"))
        return { body: { count: 0, results: [] } };
      return undefined;
    });
    wrap(<JobWizard />);
    await userEvent.type(await screen.findByLabelText(/Job title/), "Accountant");
    await userEvent.click(screen.getByRole("button", { name: "Create draft" }));
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(`/hr/jobs/${JOB}/edit?step=requirements`),
    );
  });
});

describe("JobOverview", () => {
  const inReview = () =>
    job({ status: "in_review", version: { ...job().version, status: "in_review" } });
  const common: Route[] = [
    readiness,
    (u) => (u.endsWith("/assignments/") ? { body: [] } : undefined),
    (u) =>
      u.endsWith("/events/")
        ? {
            body: [
              {
                id: "e1",
                action: "submitted",
                from_status: "draft",
                to_status: "in_review",
                actor: null,
                reason: "",
                version_number: 1,
                created_at: "2026-11-08T10:00:00Z",
              },
            ],
          }
        : undefined,
    (u) =>
      u.endsWith("/versions/")
        ? {
            body: [
              {
                id: "v1",
                number: 1,
                status: "in_review",
                change_note: "",
                submitted_at: null,
                approved_at: null,
                created_at: "",
              },
            ],
          }
        : undefined,
    (u) => (u.includes("/members/") ? { body: { count: 0, results: [] } } : undefined),
  ];

  it("HR managers can approve or request changes", async () => {
    routes(meRoute("hr_manager"), ...common, (u, init) => {
      if (u.endsWith("/approve/") && init?.method === "POST")
        return { body: job({ status: "approved" }) };
      return u === `/api/v1/hr/jobs/${JOB}/` ? { body: inReview() } : undefined;
    });
    wrap(<JobOverview jobId={JOB} />);
    const approve = await screen.findByRole("button", { name: "Approve" });
    expect(screen.getByRole("button", { name: "Request changes" })).toBeInTheDocument();
    await userEvent.click(approve);
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([u, i]) => String(u).endsWith("/approve/") && (i as RequestInit).method === "POST",
        ),
      ).toBe(true),
    );
    expect(screen.getByText("Submitted for approval")).toBeInTheDocument();
  });

  it("recruiters do not see approval actions", async () => {
    routes(meRoute("recruiter"), ...common, (u) =>
      u === `/api/v1/hr/jobs/${JOB}/` ? { body: inReview() } : undefined,
    );
    wrap(<JobOverview jobId={JOB} />);
    expect(await screen.findByRole("heading", { name: "Software Developer" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("shows the checklist when publishing is blocked (EC-JOB-01)", async () => {
    routes(meRoute("hr_manager"), ...common, (u, init) => {
      if (u.endsWith("/publish/") && init?.method === "POST")
        return {
          status: 422,
          body: {
            error: {
              code: "job_not_ready",
              message: "Not ready",
              details: {
                checks: [
                  { id: "privacy_notice", ok: false, message: "x", blocking: true, details: {} },
                ],
              },
              request_id: "r",
            },
          },
        };
      return u === `/api/v1/hr/jobs/${JOB}/`
        ? { body: job({ status: "approved", version: { ...job().version, status: "approved" } }) }
        : undefined;
    });
    wrap(<JobOverview jobId={JOB} />);
    await userEvent.click(await screen.findByRole("button", { name: "Publish now" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Publish now" }),
    );
    expect(
      await screen.findByText("Your organisation has a candidate privacy notice"),
    ).toBeInTheDocument();
  });
});

describe("public job SEO helpers", () => {
  const detail = {
    id: "j1",
    slug: "software-developer-acme",
    title: "Software Developer",
    organisation: { slug: "acme", name: "Acme", logo_url: null, verified: true },
    locations: [{ id: "l1", name: "Harare HQ", city: "Harare" }],
    workplace_type: "remote",
    employment_type: "contract",
    seniority: "mid",
    openings: 1,
    salary: { min: "1200.00", max: "1800.00", currency: "USD", period: "month" },
    summary: "Build apps",
    closes_at: "2030-03-31T21:59:00Z",
    timezone: "Africa/Harare",
    published_at: "2026-11-01T08:00:00Z",
    status: "published",
    visibility: "public",
    is_closed: false,
    accepts_applications: true,
    closed_at: null,
    start_date: null,
    version: 1,
    responsibilities_html: "<p>Code</p>",
    requirements_html: "",
    benefits_html: "",
    required_documents: ["cv"],
    essential_criteria: [],
    preferred_criteria: [],
  };

  it("builds a schema.org JobPosting", async () => {
    const { jobPostingJsonLd } = await import("@/features/jobs/public-api");
    const ld = jobPostingJsonLd(detail as never, "https://jobs.example");
    expect(ld).toMatchObject({
      "@type": "JobPosting",
      title: "Software Developer",
      employmentType: "CONTRACTOR",
      jobLocationType: "TELECOMMUTE",
      validThrough: "2030-03-31T21:59:00Z",
      url: "https://jobs.example/jobs/software-developer-acme",
      hiringOrganization: { name: "Acme", sameAs: "https://jobs.example/companies/acme" },
      baseSalary: { currency: "USD", value: { minValue: 1200, maxValue: 1800, unitText: "MONTH" } },
    });
  });

  it("escapes JSON-LD so job text cannot close the script tag", async () => {
    const { safeJsonLd } = await import("@/features/jobs/public-api");
    const out = safeJsonLd({ title: "</script><script>alert(1)</script> & co" });
    expect(out).not.toContain("<");
    expect(out).not.toContain(">");
    expect(JSON.parse(out)).toEqual({ title: "</script><script>alert(1)</script> & co" });
  });
});
