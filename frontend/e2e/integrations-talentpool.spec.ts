/**
 * v1.1 talent pool and v1.2 integrations in the browser (P16-T01):
 * - an organisation admin adds a signed webhook endpoint (private addresses are refused) and an
 *   API key that then reads the public API;
 * - a candidate joins an employer's talent pool from the privacy page, HR finds them in a talent
 *   search and invites them to another vacancy.
 */
import { expect, test, type Browser, type Page } from "@playwright/test";

import { DEMO_PASSWORD } from "./helpers";

const ORG_ADMIN = "admin@mudhotech-demo.test";
const HR = "hr@mudhotech-demo.test";
const CANDIDATE = "candidate004@core-scenario.test";

test.skip(!DEMO_PASSWORD, "DEMO_PASSWORD is required (seed_demo / seed_core_scenario accounts)");
test.describe.configure({ mode: "serial", timeout: 4 * 60_000, retries: 0 });

async function signIn(browser: Browser, email: string, next: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.waitForLoadState("networkidle");
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => url.pathname.startsWith(next), { timeout: 20_000 });
  return page;
}

test("organisation admin adds a webhook endpoint; private addresses are refused", async ({
  browser,
}) => {
  const page = await signIn(browser, ORG_ADMIN, "/hr/settings/integrations");
  const hooks = page.getByRole("region", { name: "Webhooks" });
  await expect(hooks).toBeVisible({ timeout: 20_000 });
  await hooks.getByRole("checkbox").first().check();
  await hooks.getByLabel("Endpoint URL (https)").fill("https://127.0.0.1/hook");
  await hooks.getByRole("button", { name: "Add endpoint" }).click();
  await expect(hooks.getByRole("alert")).toBeVisible();
  await expect(hooks.getByText(/Signing secret/)).toHaveCount(0);

  await hooks.getByLabel("Endpoint URL (https)").fill("https://example.com/mhrs-e2e-hook");
  await hooks.getByRole("button", { name: "Add endpoint" }).click();
  await expect(hooks.getByText(/Signing secret \(shown once/)).toBeVisible({ timeout: 15_000 });
  await expect(hooks.getByText("https://example.com/mhrs-e2e-hook").first()).toBeVisible();
});

test("an API key reads the public API and is refused once revoked", async ({ browser }) => {
  const page = await signIn(browser, ORG_ADMIN, "/hr/settings/integrations");
  const keys = page.getByRole("region", { name: "API keys" });
  await expect(keys).toBeVisible({ timeout: 20_000 });
  const name = `E2E ${Date.now()}`;
  const create = keys.getByRole("button", { name: "Create key" });
  // on slow runners the form can re-render as the page finishes loading and drop what was typed:
  // fill again until the button is enabled (it needs a name and at least one scope)
  await expect(async () => {
    await keys.getByLabel("Name").fill(name);
    const scope = keys.getByRole("checkbox").first();
    if (!(await scope.isChecked())) await scope.check();
    await expect(create).toBeEnabled({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
  await create.click({ timeout: 15_000 });
  // the new key is shown once in the status message (the list shows earlier keys as "mhrs_ab12…")
  const shown = keys.getByRole("status").locator("code");
  await expect(shown).toBeVisible({ timeout: 15_000 });
  const key = (await shown.textContent())?.trim() ?? "";
  const api = await page.request.get("/api/v1/public-api/jobs/", {
    headers: { Authorization: `Bearer ${key}` },
  });
  expect(api.status()).toBe(200);
  const jobs = await api.json();
  expect(JSON.stringify(jobs)).toContain("Software Developer");

  // revoking is immediate (no confirmation step); bounded waits so a failure names the step
  const row = keys.getByRole("listitem").filter({ hasText: name });
  await expect(row, "the new key is listed").toBeVisible({ timeout: 15_000 });
  await row.getByRole("button", { name: "Revoke" }).click({ timeout: 15_000 });
  await expect(row, "the key shows as revoked").toContainText("revoked", { timeout: 15_000 });
  const refused = await page.request.get("/api/v1/public-api/jobs/", {
    headers: { Authorization: `Bearer ${key}` },
  });
  expect(refused.status()).toBe(401);
});

test("a candidate joins the employer's talent pool", async ({ browser }) => {
  const page = await signIn(browser, CANDIDATE, "/candidate/privacy");
  const pools = page.getByRole("region", { name: "Talent pools" });
  await expect(pools).toBeVisible({ timeout: 20_000 });
  const row = pools.getByRole("listitem").filter({ hasText: "MudhoTech Demo Ltd" });
  await expect(row).toContainText(/In the pool|Not in the pool/);
  const join = row.getByRole("button", { name: "Join" });
  if (await join.isVisible()) await join.click();
  await expect(row).toContainText("In the pool", { timeout: 15_000 });
});

test("HR finds the pool member and invites them to another vacancy", async ({ browser }) => {
  const page = await signIn(browser, HR, "/hr/talent-pool");
  await page.getByLabel("Skills").fill("JavaScript"); // read from candidate004's CV (no profile)
  await page.getByRole("button", { name: "Search" }).click();
  const member = page
    .getByRole("listitem")
    .filter({ has: page.getByRole("button", { name: "Send invitation" }) })
    .first();
  await expect(member).toBeVisible({ timeout: 20_000 });
  // vacancies the person was already invited to are not offered again (re-runs on one seed)
  const vacancy = member.getByLabel("Invite to apply for");
  const options = await vacancy.locator("option:not([value=''])").count();
  test.skip(options === 0, "already invited to every open vacancy");
  await vacancy.selectOption({ index: 1 });
  await member.getByRole("button", { name: "Send invitation" }).click();
  await expect(member.getByText("Invitation sent.")).toBeVisible({ timeout: 15_000 });
});
