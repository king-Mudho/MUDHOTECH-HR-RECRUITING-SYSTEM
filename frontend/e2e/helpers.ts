import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const MAILPIT = process.env.MAILPIT_URL ?? "http://127.0.0.1:8025";
export const DEMO_PASSWORD = process.env.DEMO_PASSWORD ?? "";
export const E2E_PASSWORD = "lantern-orchard-velvet-27"; // pragma: allowlist secret - synthetic test password

export function uniqueEmail(prefix: string): string {
  return `${prefix}.${Date.now()}.${Math.floor(Math.random() * 1e6)}@e2e.mhrs.test`;
}

/** Poll Mailpit for messages to `to` and return the first link matching `pattern`. */
export async function linkFromMail(
  request: APIRequestContext,
  to: string,
  pattern: RegExp,
): Promise<string> {
  for (let attempt = 0; attempt < 60; attempt++) {
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

/** Same-origin path of an emailed link (emails use FRONTEND_URL, tests may use 127.0.0.1). */
export const pathOf = (link: string) => link.replace(/^https?:\/\/[^/]+/, "");

export async function open(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
}

export async function signIn(page: Page, email: string, password: string, next: string) {
  await open(page, `/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  // a predicate rather than a RegExp built from a variable (semgrep detect-non-literal-regexp)
  await page.waitForURL((url) => url.pathname.startsWith(next.split("?")[0]), { timeout: 20_000 });
}

export async function registerAndVerify(page: Page, request: APIRequestContext, email: string) {
  await open(page, "/register");
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(E2E_PASSWORD);
  await page.getByLabel(/Confirm password/).fill(E2E_PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your inbox" })).toBeVisible();
  const link = await linkFromMail(request, email, /https?:\/\/[^\s]+\/verify-email\?key=[^\s]+/);
  await open(page, pathOf(link));
  await page.getByRole("button", { name: "Confirm my email" }).click();
  await expect(page).toHaveURL(/\/candidate\/dashboard/, { timeout: 15_000 });
}
