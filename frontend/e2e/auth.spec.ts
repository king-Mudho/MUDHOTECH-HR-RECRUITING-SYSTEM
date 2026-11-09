/**
 * Phase 02 journeys against the running dev stack (docker compose): candidate sign-up with email
 * verification via Mailpit, and staff onboarding (create organisation -> invite -> accept).
 *
 *   E2E_BASE_URL=http://127.0.0.1:3000 MAILPIT_URL=http://127.0.0.1:8025 npx playwright test e2e/auth.spec.ts
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const MAILPIT = process.env.MAILPIT_URL ?? "http://127.0.0.1:8025";
const PASSWORD = "lantern-orchard-velvet-27";

function uniqueEmail(prefix: string): string {
  return `${prefix}.${Date.now()}.${Math.floor(Math.random() * 1e6)}@e2e.mhrs.test`;
}

/** Poll Mailpit for the newest message to `to` and return the first link matching `pattern`. */
async function linkFromMail(
  request: APIRequestContext,
  to: string,
  pattern: RegExp,
): Promise<string> {
  for (let attempt = 0; attempt < 40; attempt++) {
    const search = await request.get(`${MAILPIT}/api/v1/search`, {
      params: { query: `to:"${to}"` },
    });
    const { messages } = (await search.json()) as { messages: { ID: string }[] };
    for (const m of messages ?? []) {
      const msg = await request.get(`${MAILPIT}/api/v1/message/${m.ID}`);
      const text = ((await msg.json()) as { Text: string }).Text;
      const match = text.match(pattern);
      if (match) return match[0];
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`No email to ${to} matching ${pattern}`);
}

/** Navigate and wait until React has hydrated (dev builds compile on first hit). */
async function open(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
}

async function register(page: Page, email: string) {
  await open(page, "/register");
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page.getByLabel(/Confirm password/).fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your inbox" })).toBeVisible();
}

async function verify(page: Page, request: APIRequestContext, email: string) {
  const link = await linkFromMail(request, email, /https?:\/\/[^\s]+\/verify-email\?key=[^\s]+/);
  await open(page, link.replace(/^https?:\/\/[^/]+/, ""));
  await page.getByRole("button", { name: "Confirm my email" }).click();
  // Confirmation signs the user in (ADR-023) and redirects to their home area.
  await expect(page).toHaveURL(/\/candidate\/dashboard/, { timeout: 15_000 });
}

test.describe.configure({ mode: "serial" });

test("auth pages have no serious accessibility violations", async ({ page }) => {
  for (const path of ["/login", "/register", "/forgot-password", "/employers"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = results.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact ?? ""),
    );
    expect(serious, `${path}: ${serious.map((v) => v.id).join(", ")}`).toEqual([]);
  }
});

test("signed-out visitors are sent to login with next", async ({ page }) => {
  await page.goto("/hr/settings/team");
  await expect(page).toHaveURL(/\/login\?next=%2Fhr%2Fsettings%2Fteam/);
});

test("candidate: register -> verify email -> candidate dashboard -> sign out -> sign in", async ({
  page,
  request,
}) => {
  const email = uniqueEmail("candidate");
  await register(page, email);
  await verify(page, request, email);
  await expect(page).toHaveURL(/\/candidate\/dashboard/);
  await expect(page.getByRole("heading", { name: "Candidate dashboard" })).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).first().click();
  await expect(page).toHaveURL(/\/$/);

  await open(page, "/login");
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/candidate\/dashboard/);
});

test("staff: create organisation -> invite colleague -> colleague accepts", async ({
  browser,
  request,
}) => {
  const adminCtx = await browser.newContext();
  const admin = await adminCtx.newPage();
  const adminEmail = uniqueEmail("admin");
  await register(admin, adminEmail);
  await verify(admin, request, adminEmail);

  await open(admin, "/employers");
  await admin.getByLabel(/^Organisation name/).fill(`E2E Employer ${Date.now()}`);
  await admin.getByLabel(/^City or town/).fill("Harare");
  await admin.getByRole("button", { name: "Create organisation" }).click();
  await expect(admin).toHaveURL(/\/hr\/settings\/organisation/);
  await expect(admin.getByText(/awaiting verification/)).toBeVisible();

  await admin.getByRole("link", { name: "Team" }).click();
  const colleagueEmail = uniqueEmail("recruiter");
  await admin.getByLabel(/^Email address/).fill(colleagueEmail);
  await admin.getByLabel("Role", { exact: true }).selectOption("recruiter");
  await admin.getByRole("button", { name: "Send invitation" }).click();
  await expect(admin.getByText(`Invitation sent to ${colleagueEmail}.`)).toBeVisible();
  await expect(admin.getByRole("listitem").filter({ hasText: colleagueEmail })).toBeVisible();

  const colleagueCtx = await browser.newContext();
  const colleague = await colleagueCtx.newPage();
  const inviteLink = await linkFromMail(
    request,
    colleagueEmail,
    /https?:\/\/[^\s]+\/invitations\/[A-Za-z0-9_-]+/,
  );
  await register(colleague, colleagueEmail);
  await verify(colleague, request, colleagueEmail);
  await open(colleague, inviteLink.replace(/^https?:\/\/[^/]+/, ""));
  await expect(colleague.getByRole("heading", { name: /^Join E2E Employer/ })).toBeVisible();
  await colleague.getByRole("button", { name: "Accept invitation" }).click();
  await expect(colleague.getByRole("heading", { name: /^Welcome to E2E Employer/ })).toBeVisible();
  await colleague.getByRole("button", { name: "Go to HR dashboard" }).click();
  await expect(colleague.getByRole("heading", { name: "HR dashboard" })).toBeVisible();

  await admin.reload();
  await expect(admin.getByText(colleagueEmail).first()).toBeVisible();
  await adminCtx.close();
  await colleagueCtx.close();
});
