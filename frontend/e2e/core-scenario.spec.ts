/**
 * MVP core scenario in the browser (P08-T13, Phase 08 exit criterion).
 *
 * 100 synthetic applications to the demo Software Developer vacancy are processed by the workers;
 * the HR manager filters them, verifies two claims, asks one applicant for clarification, builds
 * and approves a shortlist of ten; after the (1 minute, CI) notification delay Mailpit holds ten
 * "shortlisted" emails and nobody else was told an outcome.
 *
 * Needs the Docker stack with workers, Mailpit and:
 *   DEMO_PASSWORD=... python manage.py seed_demo
 *   DEMO_PASSWORD=... python manage.py seed_core_scenario --count 100 --delay-minutes 1
 *   E2E_BASE_URL=http://127.0.0.1:3000 MAILPIT_URL=http://127.0.0.1:8025 DEMO_PASSWORD=... \
 *     npx playwright test e2e/core-scenario.spec.ts --project=chromium
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const PASSWORD = process.env.DEMO_PASSWORD ?? "";
const MAILPIT = process.env.MAILPIT_URL ?? "http://127.0.0.1:8025";
const HR = "hr@mudhotech-demo.test";

test.describe.configure({ mode: "serial", timeout: 15 * 60_000 });

async function signIn(page: Page, email: string) {
  await page.goto("/login?next=/hr/dashboard");
  await page.waitForLoadState("networkidle");
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/hr\/dashboard/, { timeout: 20_000 });
}

async function context(page: Page): Promise<{ org: string; job: string }> {
  const me = await (await page.request.get("/api/v1/me/")).json();
  const org = me.active_organisation_id as string;
  const jobs = await (
    await page.request.get("/api/v1/hr/jobs/?search=Software%20Developer", {
      headers: { "X-Org-Id": org },
    })
  ).json();
  return { org, job: jobs.results[0].id as string };
}

async function waitForProcessing(request: APIRequestContext, org: string, job: string) {
  await expect
    .poll(
      async () => {
        const res = await request.get(
          `/api/v1/hr/jobs/${job}/applications/?status=submitted,processing&page_size=1`,
          { headers: { "X-Org-Id": org } },
        );
        return (await res.json()).count as number;
      },
      { timeout: 10 * 60_000, intervals: [5_000] },
    )
    .toBe(0);
}

async function mailCount(request: APIRequestContext, query: string): Promise<number> {
  const res = await request.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(query)}`);
  return ((await res.json()).messages_count as number) ?? 0;
}

test("core scenario: 100 applicants to an approved shortlist of ten", async ({ page }) => {
  test.skip(!PASSWORD, "DEMO_PASSWORD not set");
  await signIn(page, HR);
  const { org, job } = await context(page);
  await waitForProcessing(page.request, org, job);

  // filter: recommended applicants (AI suggestion), newest data from the server
  await page.goto(`/hr/jobs/${job}/applications`);
  await page.getByRole("button", { name: "Recommended" }).click();
  const rows = page.locator("tbody tr");
  await expect(rows.first()).toBeVisible();
  expect(await rows.count()).toBeGreaterThanOrEqual(10);

  // verify two claims on two applicants' review pages
  for (const n of [0, 1]) {
    await page.goto(`/hr/jobs/${job}/applications`);
    await page.getByRole("button", { name: "Recommended" }).click();
    await page.locator("tbody tr").nth(n).getByRole("link").first().click();
    await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
    await page.getByRole("button", { name: "Confirm" }).first().click();
    await expect(page.getByText(/new evaluation version is being prepared/)).toBeVisible();
  }

  // ask one applicant who needs review for clarification (bulk bar with one selected)
  await page.goto(`/hr/jobs/${job}/applications`);
  await page.getByRole("button", { name: "Needs review" }).click();
  await page.locator("tbody tr").first().getByRole("checkbox").check();
  await page.getByRole("button", { name: "Request clarification" }).click();
  await page.getByLabel("Question for the applicants").fill("Please describe a Django project.");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText(/1 application updated/)).toBeAttached();

  // shortlist of ten: propose, decide, submit, approve (dual control is off in the demo)
  await page.goto(`/hr/jobs/${job}/shortlist`);
  await page.getByLabel("Desired shortlist size").fill("10");
  await page.getByRole("button", { name: "Propose shortlist" }).click();
  const suggested = page.locator("section", {
    has: page.getByRole("heading", { name: /^Suggested/ }),
  });
  for (let i = 0; i < 10; i++) {
    await suggested
      .getByRole("group", { name: /^Decision for/ })
      .nth(i)
      .getByRole("button", { name: "Shortlist" })
      .click();
    await expect(page.getByText(new RegExp(`^${i + 1} shortlisted`))).toBeVisible();
  }
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await page.getByRole("button", { name: "Approve shortlist" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("checkbox", { name: /Leave .* in review/ }).check();
  await dialog.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();

  // after the delay: ten outcome emails to synthetic candidates, no "not selected" ones
  await expect
    .poll(
      () =>
        mailCount(
          page.request,
          'to:"core-scenario.test" subject:"Good news about your application"',
        ),
      {
        timeout: 4 * 60_000,
        intervals: [10_000],
      },
    )
    .toBeGreaterThanOrEqual(10);
  expect(
    await mailCount(page.request, 'to:"core-scenario.test" subject:"Update on your application"'),
  ).toBe(0);
});
