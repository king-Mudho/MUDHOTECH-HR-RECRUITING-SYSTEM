/**
 * Accessibility pass on the candidate and HR core journeys (P09-T13, docs/accessibility/AUDIT.md).
 *
 * axe (WCAG 2.0/2.1/2.2 A + AA) must report zero serious or critical violations on every page of
 * the journeys, plus keyboard checks: the skip link moves focus to the main content and every
 * interactive element reached by Tab has a visible focus indicator.
 *
 * Needs the stack seeded with `seed_demo` and `seed_core_scenario` (nightly workflow), and
 * DEMO_PASSWORD. Runs after core-scenario.spec.ts, so the shortlist pages have data.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { settleForAxe } from "./a11y";
import { hrContext } from "./hr-context";

const PASSWORD = process.env.DEMO_PASSWORD ?? "";
const HR = "hr@mudhotech-demo.test";
const CANDIDATE = "candidate001@core-scenario.test";

test.skip(!PASSWORD, "DEMO_PASSWORD is required (seed_demo / seed_core_scenario accounts)");
test.describe.configure({ mode: "serial", timeout: 5 * 60_000 });

async function signIn(page: Page, email: string, next: string) {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.waitForLoadState("networkidle");
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(new RegExp(next.replace(/\//g, "\\/")), { timeout: 20_000 });
}

async function axe(page: Page, label: string): Promise<string[]> {
  await page.waitForLoadState("networkidle");
  await settleForAxe(page);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${label} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function sweep(page: Page, paths: string[]): Promise<void> {
  const problems: string[] = [];
  for (const path of paths) {
    await page.goto(path);
    await expect(page.locator("main").first()).toBeVisible({ timeout: 20_000 });
    problems.push(...(await axe(page, path)));
  }
  expect(problems).toEqual([]);
}

/** Tab through the page: focus must always be visible (outline or ring) and never trapped. */
async function keyboardWalk(page: Page, steps = 25): Promise<void> {
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: /skip to (main )?content/i });
  if (await skip.isVisible()) {
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#main-content$/);
    await expect(page.locator("#main-content")).toHaveCount(1); // the skip target exists
  }
  const seen = new Set<string>();
  for (let i = 0; i < steps; i += 1) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const style = getComputedStyle(el);
      const visible =
        (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0) ||
        style.boxShadow !== "none";
      return { key: el.outerHTML.slice(0, 80), visible };
    });
    if (!info) continue;
    expect(info.visible, `focus indicator missing on ${info.key}`).toBe(true);
    seen.add(info.key);
  }
  expect(seen.size).toBeGreaterThan(1); // focus moved; no keyboard trap
}

test("candidate journey pages have no serious accessibility violations", async ({ page }) => {
  await signIn(page, CANDIDATE, "/candidate/dashboard");
  await sweep(page, [
    "/candidate/dashboard",
    "/candidate/applications",
    "/candidate/profile",
    "/candidate/privacy",
    "/how-we-use-ai",
    "/jobs",
  ]);
  await page.goto("/candidate/applications");
  await keyboardWalk(page);
});

test("HR journey pages have no serious accessibility violations", async ({ page }) => {
  await signIn(page, HR, "/hr/dashboard");
  const { job } = await hrContext(page);
  await sweep(page, [
    "/hr/dashboard",
    "/hr/jobs",
    `/hr/jobs/${job}/applications`,
    `/hr/jobs/${job}/shortlist`,
    "/hr/settings/privacy",
    "/hr/settings/audit",
  ]);
  await page.goto(`/hr/jobs/${job}/applications`);
  await keyboardWalk(page, 40);
});
