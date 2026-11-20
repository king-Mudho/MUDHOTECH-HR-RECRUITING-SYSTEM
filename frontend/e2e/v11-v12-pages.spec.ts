/**
 * v1.1 / v1.2 screens in the browser (P16-T01): every page of interviews, offers, talent pool,
 * reports, billing, integrations and the platform console loads for the role that uses it, shows
 * no error state, logs no console errors and has no serious axe violations. Also checks the
 * report export, the language switcher and the candidate's talent pool settings.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

import { settleForAxe } from "./a11y";
import { DEMO_PASSWORD } from "./helpers";

const HR = "hr@mudhotech-demo.test";
const ORG_ADMIN = "admin@mudhotech-demo.test";
const PLATFORM = "admin@mhrs-demo.test";
const CANDIDATE = "candidate003@core-scenario.test";

test.skip(!DEMO_PASSWORD, "DEMO_PASSWORD is required (seed_demo accounts)");
test.describe.configure({ mode: "default", timeout: 6 * 60_000 });

type Session = { page: Page; errors: string[] };

async function signIn(browser: Browser, email: string, next: string): Promise<Session> {
  const page = await (await browser.newContext()).newPage();
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`${page.url()}: ${m.text()}`);
  });
  page.on("pageerror", (e) => errors.push(`${page.url()}: ${e.message}`));
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.waitForLoadState("networkidle");
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => url.pathname.startsWith(next), { timeout: 20_000 });
  return { page, errors };
}

async function check(s: Session, path: string, heading: RegExp | string): Promise<string[]> {
  const { page } = s;
  await page.goto(path);
  await expect(page.locator("main").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible({
    timeout: 20_000,
  });
  await page.waitForLoadState("networkidle");
  const problems: string[] = [];
  for (const text of ["Something went wrong", "You don't have access", "Page not found"]) {
    if ((await page.getByText(text).count()) > 0) problems.push(`${path}: shows "${text}"`);
  }
  await settleForAxe(page);
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  for (const v of axe.violations.filter((x) => x.impact === "serious" || x.impact === "critical"))
    problems.push(`${path} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  return problems;
}

function consoleProblems(s: Session): string[] {
  // a 401/403 probe before sign-in completes is expected; anything else is a defect
  return s.errors.filter((e) => !/status of 40[13]/.test(e));
}

test("HR manager: interviews, offers, talent pool, reports and settings pages", async ({
  browser,
}) => {
  const s = await signIn(browser, HR, "/hr/dashboard");
  const problems = [
    ...(await check(s, "/hr/interviews", "Interviews")),
    ...(await check(s, "/hr/offers", "Offers")),
    ...(await check(s, "/hr/talent-pool", /Talent pool/)),
    ...(await check(s, "/hr/reports", /Reports/)),
    ...(await check(s, "/hr/settings/notifications", "Settings")),
  ];
  expect(problems).toEqual([]);
  expect(consoleProblems(s)).toEqual([]);
});

test("HR manager exports a report as CSV", async ({ browser }) => {
  const s = await signIn(browser, HR, "/hr/reports");
  const { page } = s;
  await expect(page.getByRole("heading", { level: 1, name: /Reports/ })).toBeVisible();
  await page.getByLabel("Format").selectOption({ label: "CSV" });
  await page.getByRole("button", { name: "Prepare export" }).click();
  // prepared by the reports worker, then a 15-minute download link
  const download = page.getByRole("button", { name: /^Download \(\d+ rows\)/ }).first();
  await expect(download).toBeVisible({ timeout: 90_000 });
  const [file] = await Promise.all([page.waitForEvent("download"), download.click()]);
  expect(file.suggestedFilename()).toMatch(/\.csv$/);
  expect(consoleProblems(s)).toEqual([]);
});

test("organisation admin: billing, integrations, team and policies", async ({ browser }) => {
  const s = await signIn(browser, ORG_ADMIN, "/hr/dashboard");
  const problems = [
    ...(await check(s, "/hr/settings/billing", "Settings")),
    ...(await check(s, "/hr/settings/integrations", "Settings")),
    ...(await check(s, "/hr/settings/team", "Settings")),
    ...(await check(s, "/hr/settings/policies", "Settings")),
    ...(await check(s, "/hr/settings/audit", "Settings")),
  ];
  expect(problems).toEqual([]);
  expect(consoleProblems(s)).toEqual([]);
});

test("platform admin: console pages", async ({ browser }) => {
  const s = await signIn(browser, PLATFORM, "/admin/dashboard");
  const problems: string[] = [];
  for (const [path, heading] of [
    ["/admin/dashboard", /./],
    ["/admin/organisations", /Organisations/],
    ["/admin/users", /Users/],
    ["/admin/feature-flags", /Feature flags/],
    ["/admin/taxonomy", /Skills|Taxonomy/],
    ["/admin/plans", /Plans/],
    ["/admin/dead-letters", /Dead letters|Failed/],
    ["/admin/system", /System/],
    ["/admin/model-registry", "AI governance"],
    ["/admin/support-access", /Support/],
  ] as const)
    problems.push(...(await check(s, path, heading)));
  expect(problems).toEqual([]);
  expect(consoleProblems(s)).toEqual([]);
});

test("candidate: talent pool settings and language switcher", async ({ browser }) => {
  const s = await signIn(browser, CANDIDATE, "/candidate/dashboard");
  const problems = [
    ...(await check(s, "/candidate/privacy", /Privacy/)),
    ...(await check(s, "/candidate/settings", /Settings/)),
  ];
  expect(problems).toEqual([]);
  const { page } = s;
  // the switcher sits in the public footer; the choice (a cookie) follows the person everywhere
  await page.goto("/");
  const switcher = page.getByRole("combobox", { name: "Language" });
  await switcher.selectOption("sn");
  await expect(page.locator("html")).toHaveAttribute("lang", "sn", { timeout: 15_000 });
  await expect(page.getByRole("combobox", { name: "Mutauro" })).toBeVisible(); // label in Shona
  await page.goto("/candidate/dashboard");
  await expect(page.locator("html")).toHaveAttribute("lang", "sn", { timeout: 15_000 });
  await page.screenshot({ path: test.info().outputPath("shona-dashboard.png"), fullPage: true });
  await page.goto("/");
  await page.getByRole("combobox", { name: "Mutauro" }).selectOption("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en", { timeout: 15_000 });
  expect(consoleProblems(s)).toEqual([]);
});
