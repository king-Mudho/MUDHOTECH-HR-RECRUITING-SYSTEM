/**
 * Phase 04 journey against the running dev stack: a candidate registers, verifies their email
 * through Mailpit, applies for the seeded Software Developer vacancy with a CV and answers, gets a
 * receipt, cannot apply twice, and withdraws. Also checks the wizard at 360 px with axe.
 *
 * Needs `manage.py seed_demo`, Mailpit, S3 and a Celery worker (outbox relay, scan, email):
 *   E2E_BASE_URL=http://127.0.0.1:3000 MAILPIT_URL=http://127.0.0.1:8025 npx playwright test e2e/apply.spec.ts --project=mobile
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const MAILPIT = process.env.MAILPIT_URL ?? "http://127.0.0.1:8025";
const PASSWORD = "lantern-orchard-velvet-27";

/** A small, valid one-page PDF (synthetic CV; no personal data). */
function syntheticCv(): Buffer {
  const text = "Synthetic CV - Software Developer - Python, Django, PostgreSQL";
  const stream = `BT /F1 12 Tf 72 720 Td (${text}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(pdf.length);
    pdf += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const o of offsets) pdf += `${String(o).padStart(10, "0")} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf, "latin1");
}

function uniqueEmail(prefix: string): string {
  return `${prefix}.${Date.now()}.${Math.floor(Math.random() * 1e6)}@e2e.mhrs.test`;
}

async function mailText(
  request: APIRequestContext,
  to: string,
  pattern: RegExp,
): Promise<RegExpMatchArray> {
  for (let attempt = 0; attempt < 60; attempt++) {
    const search = await request.get(`${MAILPIT}/api/v1/search`, {
      params: { query: `to:"${to}"` },
    });
    const { messages } = (await search.json()) as { messages: { ID: string }[] };
    for (const m of messages ?? []) {
      const msg = await request.get(`${MAILPIT}/api/v1/message/${m.ID}`);
      const text = ((await msg.json()) as { Text: string }).Text;
      const match = text.match(pattern);
      if (match) return match;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`No email to ${to} matching ${pattern}`);
}

async function open(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
}

async function registerAndVerify(page: Page, request: APIRequestContext, email: string) {
  await open(page, "/register");
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page.getByLabel(/Confirm password/).fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your inbox" })).toBeVisible();
  const [link] = await mailText(request, email, /https?:\/\/[^\s]+\/verify-email\?key=[^\s]+/);
  await open(page, link!.replace(/^https?:\/\/[^/]+/, ""));
  await page.getByRole("button", { name: "Confirm my email" }).click();
  await expect(page).toHaveURL(/\/candidate\/dashboard/, { timeout: 15_000 });
}

async function expectNoSeriousA11y(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact ?? ""),
  );
  expect(serious, `${label}: ${serious.map((v) => v.id).join(", ")}`).toEqual([]);
}

const next = (page: Page) => page.getByRole("button", { name: "Save and continue" }).click();

test.describe.configure({ mode: "serial" });

test("candidate applies with CV and answers, gets a receipt, cannot apply twice, withdraws", async ({
  page,
  request,
}) => {
  test.setTimeout(180_000);
  const pageErrors: string[] = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));
  await page.setViewportSize({ width: 360, height: 780 });
  const email = uniqueEmail("applicant");
  await registerAndVerify(page, request, email);

  // Find the seeded vacancy on the public board and start applying.
  await open(page, "/jobs?q=Software%20Developer");
  await page.getByRole("link", { name: "Software Developer" }).first().click();
  await page.getByRole("link", { name: "Apply now" }).first().click();
  await expect(page).toHaveURL(/\/apply\//);
  const applyUrl = new URL(page.url()).pathname;

  // Step 1 — contact details and privacy notice.
  await expect(page.getByText("Step 1 of 5 — Contact details & privacy")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Contact details & privacy" })).toBeFocused();
  await expectNoSeriousA11y(page, "contact step");
  await page.getByLabel(/First name/).fill("Rudo");
  await page.getByLabel(/Last name/).fill("Moyo");
  await page.getByLabel("Phone number").fill("+263771234567");
  await next(page);

  // Step 2 — profile summary.
  await expect(page.getByText("Step 2 of 5 — Your profile")).toBeVisible();
  await next(page);

  // Step 3 — CV upload (checked for safety before anyone opens it).
  await expect(page.getByText("Step 3 of 5 — Documents")).toBeVisible();
  await page.getByLabel("Upload a file").setInputFiles({
    name: "synthetic-cv.pdf",
    mimeType: "application/pdf",
    buffer: syntheticCv(),
  });
  await expect(page.getByText(/synthetic-cv\.pdf is (ready|uploaded)/)).toBeVisible({
    timeout: 60_000,
  });
  await expectNoSeriousA11y(page, "documents step");
  await next(page);

  // Step 4 — questions, keyboard only for the choice question.
  await expect(page.getByText("Step 4 of 5 — Questions")).toBeVisible();
  await page
    .getByLabel(/Describe a Python project/)
    .fill("Built a Django REST API with tests for a payroll service.");
  await page
    .getByLabel(/Give an example of an API you designed/)
    .fill("A jobs API with list, detail and apply endpoints.");
  await page.getByRole("checkbox", { name: "PostgreSQL" }).focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("checkbox", { name: "PostgreSQL" })).toBeChecked();
  await page.getByLabel(/notice period/).fill("4");
  await expectNoSeriousA11y(page, "questions step");
  await next(page);

  // Step 5 — review, consent and submit.
  await expect(page.getByText("Step 5 of 5 — Review & submit")).toBeVisible();
  await expect(page.getByText("synthetic-cv.pdf")).toBeVisible();
  const submit = page.getByRole("button", { name: "Submit application" });
  await expect(submit).toBeDisabled();
  await page.getByRole("checkbox", { name: /agree to it being used/ }).check();
  await expectNoSeriousA11y(page, "review step");
  await submit.click();
  const confirmation = page.getByText(/Your reference is (MHRS-[A-Z0-9]+-\d{4}-\d{6})/);
  await expect(confirmation).toBeVisible({ timeout: 30_000 });
  const reference = (await confirmation.textContent())!.match(/MHRS-[A-Z0-9]+-\d{4}-\d{6}/)![0];

  // Receipt email quotes the reference.
  await mailText(request, email, new RegExp(reference));

  // A second attempt points to the existing application instead of creating a duplicate.
  await open(page, applyUrl);
  await expect(page.getByText(/already (applied|submitted)/).first()).toBeVisible();

  // Withdraw from the candidate portal.
  await page.getByRole("link", { name: "Open your application" }).click();
  await expect(page.getByText(reference)).toBeVisible();
  await page.getByRole("button", { name: "Withdraw application" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox").fill("Accepted another offer");
  await dialog.getByRole("button", { name: "Withdraw application" }).click();
  await expect(page.getByText("Withdrawn").first()).toBeVisible();
  expect(pageErrors, "uncaught page errors (e.g. hydration)").toEqual([]);
});

test("signed-out visitors are asked to sign in before applying", async ({ page }) => {
  await open(page, "/jobs?q=Software%20Developer");
  await page.getByRole("link", { name: "Software Developer" }).first().click();
  await page.getByRole("link", { name: "Apply now" }).first().click();
  await expect(page).toHaveURL(/\/login\?next=%2Fapply%2F/);
});
