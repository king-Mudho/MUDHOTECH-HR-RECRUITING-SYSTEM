import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("home page renders with branding and no serious a11y violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(
    page.getByText("MUDHOTECH HR RECRUITING SYSTEM").filter({ visible: true }).first(),
  ).toBeVisible();
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact ?? ""),
  );
  expect(serious).toEqual([]);
});

test("API is reachable through the same-origin proxy", async ({ request }) => {
  const res = await request.get("/api/v1/");
  expect(res.ok()).toBeTruthy();
  expect((await res.json()).name).toBe("MUDHOTECH HR RECRUITING SYSTEM");
});
