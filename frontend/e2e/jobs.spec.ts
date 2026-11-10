/**
 * Phase 03 journey (exit criterion 1): a recruiter creates a vacancy with the wizard, an HR manager
 * approves and publishes it, and it is searchable on the public job board.
 *
 * Needs the demo data: `DEMO_PASSWORD=... python manage.py seed_demo` (synthetic accounts).
 *
 *   E2E_BASE_URL=http://127.0.0.1:3000 DEMO_PASSWORD=... npx playwright test e2e/jobs.spec.ts
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { settleForAxe } from "./a11y";

const PASSWORD = process.env.DEMO_PASSWORD ?? "";

async function signIn(page: Page, email: string) {
  await page.goto("/login?next=/hr/jobs");
  await page.waitForLoadState("networkidle");
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/^[^?]*\/hr\/jobs$/, { timeout: 15_000 });
}

async function expectNoSeriousA11yViolations(page: Page) {
  await settleForAxe(page);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  expect(
    serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
  ).toEqual([]);
}

test.describe.configure({ mode: "serial" });
test.skip(!PASSWORD, "DEMO_PASSWORD is required (seed_demo accounts)");

const title = `E2E Data Engineer ${Date.now()}`;
let jobUrl = "";

test("recruiter creates a vacancy with the wizard and submits it", async ({ page }) => {
  await signIn(page, "recruiter@mudhotech-demo.test");
  await expect(page.getByRole("heading", { name: "Vacancies" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Software Developer" })).toBeVisible();
  await expectNoSeriousA11yViolations(page);

  await page.getByRole("link", { name: "New vacancy" }).first().click();
  await expect(page.getByRole("heading", { name: "New vacancy" })).toBeVisible();
  await page.getByLabel(/Job title/).fill(title);
  await page.getByLabel(/Applications close/).fill("2030-06-30T17:00");
  await page.getByRole("checkbox", { name: /Harare HQ/ }).check();
  await page.getByLabel("Short summary").fill("Build data pipelines for our clients.");
  await page.getByRole("textbox", { name: "Responsibilities" }).click();
  await page.keyboard.type("Design and run reliable data pipelines.");
  await expectNoSeriousA11yViolations(page);
  await page.getByRole("button", { name: "Create draft" }).click();
  await expect(page).toHaveURL(/\/edit\?step=requirements/, { timeout: 15_000 });
  jobUrl = page.url().replace(/\/edit\?.*$/, "");

  await page.getByRole("button", { name: "Add requirement" }).click();
  await page.getByRole("combobox", { name: "Requirement" }).fill("Python");
  await page.getByRole("radio", { name: "Essential" }).check();
  await page.getByLabel(/Why is this needed/).fill("Our pipelines are written in Python.");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page).toHaveURL(/step=questions/);

  await page.getByLabel("Insert from question bank").selectOption("right_to_work");
  await expect(page.getByLabel("Question text")).toHaveValue(/right to work/);
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page).toHaveURL(/step=rubric/);
  await expect(page.getByTestId("rubric-total")).toContainText("Total: 100%");
  await page.getByRole("button", { name: "Save and continue" }).click();
  await expect(page).toHaveURL(/step=preview/);

  await expect(page.getByRole("heading", { name: title, level: 2 })).toBeVisible();
  await expect(page.getByText("Everything required is in place.").first()).toBeVisible();
  await expectNoSeriousA11yViolations(page);
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page).toHaveURL(new RegExp(`${jobUrl.replace(/[/.]/g, "\\$&")}$`), {
    timeout: 15_000,
  });
  await expect(page.getByText("In review").first()).toBeVisible();
});

test("HR manager approves and publishes; the vacancy is publicly searchable", async ({
  page,
  request,
}) => {
  test.skip(!jobUrl, "previous step failed");
  await signIn(page, "hr@mudhotech-demo.test");
  await page.goto(jobUrl);
  await page.getByRole("button", { name: "Approve" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved").first()).toBeVisible({ timeout: 15_000 });
  await expectNoSeriousA11yViolations(page);
  await page.getByRole("button", { name: "Publish now" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Publish now" }).click();
  await expect(page.getByText("Published").first()).toBeVisible({ timeout: 15_000 });

  const res = await request.get("/api/v1/jobs/", { params: { q: title } });
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as { results: { title: string }[] };
  expect(body.results.map((r) => r.title)).toContain(title);
});

test("the public board finds the new vacancy by keyword", async ({ page }) => {
  test.skip(!jobUrl, "previous step failed");
  await page.goto("/");
  await page.getByRole("searchbox", { name: "Keywords" }).fill(title);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page).toHaveURL(/\/jobs\?q=/);
  const card = page.getByRole("link", { name: title });
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute("href", /^\/jobs\/e2e-data-engineer-/);
  await expectNoSeriousA11yViolations(page);
});

test("a closed vacancy shows a closed banner and is not indexed", async ({ page }) => {
  test.skip(!jobUrl, "previous step failed");
  await signIn(page, "hr@mudhotech-demo.test");
  await page.goto(jobUrl);
  await page.getByRole("button", { name: "Close vacancy" }).click();
  await page
    .getByRole("dialog")
    .getByLabel(/Reason/)
    .fill("Position filled");
  await page.getByRole("dialog").getByRole("button", { name: "Close vacancy" }).click();
  await expect(page.getByText("Closed").first()).toBeVisible({ timeout: 15_000 });
  const slug = (await page.getByRole("link", { name: "View public page" }).getAttribute("href"))!;

  // First public visit after closing (public pages cache for 60 s per URL).
  await page.goto(slug);
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.getByText("Applications have closed")).toBeVisible();
  await expect(page.getByRole("link", { name: "Apply now" })).toHaveCount(0);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  const ld = JSON.parse((await page.locator('script[type="application/ld+json"]').textContent())!);
  expect(ld["@type"]).toBe("JobPosting");
  await expectNoSeriousA11yViolations(page);
});
