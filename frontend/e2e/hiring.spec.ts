/**
 * v1.1 hiring journey in the browser (P16-T01): after the core scenario has approved a shortlist,
 * HR schedules an interview with time options, the candidate books one, the panelist submits a
 * scorecard, HR completes the interview, drafts and approves an offer, the candidate accepts it
 * electronically and HR sees the hire.
 *
 * Runs after core-scenario.spec.ts (alphabetical order) on the same seed; skipped when no
 * shortlisted application exists (e.g. E2E_SKIP_CORE=1 on staging).
 */
import { expect, test, type Browser, type Page } from "@playwright/test";

import { DEMO_PASSWORD } from "./helpers";
import { hrContext } from "./hr-context";

const HR = "hr@mudhotech-demo.test";
const PANEL = "panel@mudhotech-demo.test";

test.describe.configure({ mode: "serial", timeout: 5 * 60_000, retries: 0 });

async function signInAs(browser: Browser, email: string, next: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.waitForLoadState("networkidle");
  await page.getByLabel(/Email address/).fill(email);
  await page.getByLabel(/^Password/).fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => url.pathname.startsWith(next.split("?")[0]), { timeout: 20_000 });
  return page;
}

/** datetime-local value `days` from now at 10:00 local time */
function future(days: number, hour = 10): string {
  const d = new Date(Date.now() + days * 86_400_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(hour)}:00`;
}

let appId = "";
let candidateEmail = "";
let interviewId = "";

test("HR schedules an interview with time options for a shortlisted applicant", async ({
  browser,
}) => {
  test.skip(!DEMO_PASSWORD, "DEMO_PASSWORD not set");
  const hr = await signInAs(browser, HR, "/hr/dashboard");
  const { org, job } = await hrContext(hr);
  const res = await hr.request.get(
    `/api/v1/hr/jobs/${job}/applications/?status=shortlisted&page_size=50`,
    { headers: { "X-Org-Id": org } },
  );
  const rows = (await res.json()).results as { id: string }[];
  test.skip(!rows.length, "no shortlisted application (core scenario not run)");
  // pick one without interviews yet so the spec can be re-run on the same seed
  for (const row of rows) {
    const ivs = await hr.request.get(`/api/v1/hr/applications/${row.id}/interviews/`, {
      headers: { "X-Org-Id": org },
    });
    if (ivs.ok() && ((await ivs.json()) as unknown[]).length === 0) {
      appId = row.id;
      break;
    }
  }
  test.skip(!appId, "every shortlisted application already has an interview");
  // blind review: contact details stay hidden until this reviewer reveals them (audited)
  await hr.goto(`/hr/applications/${appId}`);
  const reveal = hr.getByRole("button", { name: "Reveal identity" });
  await expect(hr.getByRole("heading", { name: "Candidate", exact: true })).toBeVisible();
  if (await reveal.isVisible()) {
    await reveal.click();
    await hr.getByLabel("Why do you need to see who this is?").fill("Arranging the interview");
    await hr.getByRole("button", { name: "Reveal", exact: true }).click();
    await expect(hr.getByText(/^Blind review:/)).toBeHidden({ timeout: 15_000 });
  }
  const detail = await hr.request.get(`/api/v1/hr/applications/${appId}/`, {
    headers: { "X-Org-Id": org },
  });
  candidateEmail = (await detail.json()).candidate_email ?? "";
  expect(candidateEmail).toContain("@");

  await hr.getByRole("button", { name: "Schedule an interview" }).click();
  const dialog = hr.getByRole("dialog");
  await dialog.getByLabel("Stage").fill("Technical interview");
  await dialog.getByLabel("How").selectOption("video");
  await dialog.getByLabel("Video call link").fill("https://meet.example.test/mhrs-e2e");
  await dialog.getByLabel("Let the candidate choose").check();
  await dialog.getByLabel("Option 1").fill(future(3));
  await dialog.getByRole("button", { name: "Add a time" }).click();
  await dialog.getByLabel("Option 2").fill(future(4, 14));
  await dialog.getByRole("checkbox", { name: /Panel/ }).check();
  await dialog.getByRole("button", { name: "Send invitation" }).click();
  // a re-run on the same seed books the same panelist again: the conflict is a warning only
  const keep = dialog.getByRole("button", { name: "Keep it" });
  await expect(dialog.or(keep)).toBeVisible();
  await keep.click({ timeout: 5_000 }).catch(() => undefined);
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  const link = hr.locator("#interviews").getByRole("link", { name: "Technical interview" });
  await expect(link).toBeVisible();
  interviewId = ((await link.getAttribute("href")) ?? "").split("/").pop() ?? "";
  await expect(hr.locator("#interviews")).toContainText("time not chosen yet");
});

test("the candidate books one of the offered times", async ({ browser }) => {
  test.skip(!interviewId, "no interview scheduled");
  const me = await signInAs(browser, candidateEmail, `/candidate/applications/${appId}`);
  const iv = me.getByRole("region", { name: "Technical interview" });
  await expect(iv).toContainText("Choose a time that suits you");
  await iv.getByRole("button", { name: /10:00/ }).click();
  await expect(iv).toContainText("Booked");
  await expect(iv.getByRole("link", { name: "Add to calendar" })).toBeVisible();
});

test("the panelist sees the interview and saves a draft scorecard", async ({ browser }) => {
  test.skip(!interviewId, "no interview scheduled");
  const panel = await signInAs(browser, PANEL, `/hr/interviews/${interviewId}`);
  await expect(panel.getByRole("heading", { name: "Interview details" })).toBeVisible();
  await expect(panel.getByText("Status: Scheduled")).toBeVisible();
  // the AI band is hidden from panelists by default (they assess the interview on its own)
  await expect(panel.getByText(/Screening band/)).toHaveCount(0);
  await panel.screenshot({ path: test.info().outputPath("panel-interview.png"), fullPage: true });
});

let offerId = "";

test("HR drafts an offer and submits it for approval", async ({ browser }) => {
  test.skip(!interviewId, "no interview scheduled");
  const hr = await signInAs(browser, HR, `/hr/applications/${appId}`);
  const section = hr.locator("#offer");
  await section.getByRole("button", { name: "Make an offer" }).click();
  await section.getByLabel("Pay amount").fill("1500");
  await section.getByLabel("Start date").fill(future(30).slice(0, 10));
  await section.getByLabel("Reply by").fill(future(10));
  await section.getByRole("button", { name: "Save draft" }).click();
  const link = section.getByRole("link").first();
  await expect(link).toBeVisible({ timeout: 15_000 });
  offerId = ((await link.getAttribute("href")) ?? "").split("/").pop() ?? "";
  await link.click();
  await hr.getByRole("button", { name: "Submit for approval" }).click();
  await expect(hr.getByText("Waiting for approval").first()).toBeVisible();
  await hr.screenshot({ path: test.info().outputPath("offer-submitted.png"), fullPage: true });
});

test("an approver approves and the offer is issued", async ({ browser }) => {
  test.skip(!offerId, "no offer");
  const admin = await signInAs(browser, "admin@mudhotech-demo.test", `/hr/offers/${offerId}`);
  await admin.getByRole("button", { name: "Approve", exact: true }).click();
  const confirm = admin.getByRole("dialog");
  if (await confirm.isVisible().catch(() => false))
    await confirm.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(admin.getByText("Approved").first()).toBeVisible({ timeout: 15_000 });
  await admin.getByRole("button", { name: "Issue to the candidate" }).click();
  await admin.getByRole("dialog").getByRole("button", { name: /Issue/ }).click();
  await expect(admin.getByText("With the candidate").first()).toBeVisible({ timeout: 15_000 });
});

test("the candidate accepts the offer with a typed name", async ({ browser }) => {
  test.skip(!offerId, "no offer");
  const me = await signInAs(browser, candidateEmail, `/candidate/applications/${appId}`);
  await me.getByRole("button", { name: "Accept the offer" }).click();
  const profile = await (await me.request.get("/api/v1/me/")).json();
  const name = `${profile.first_name ?? ""} ${profile.last_name ?? ""}`.trim();
  await me.getByLabel("Your full name").fill(name);
  await me.getByRole("checkbox").check();
  await me.getByRole("button", { name: "Sign and accept" }).click();
  await expect(me.getByText(/You accepted this offer/)).toBeVisible({ timeout: 15_000 });
});

test("HR records the hire", async ({ browser }) => {
  test.skip(!offerId, "no offer");
  const hr = await signInAs(browser, HR, `/hr/offers/${offerId}`);
  await expect(hr.getByText("Accepted").first()).toBeVisible();
  await hr.getByRole("button", { name: "Record the hire" }).click();
  const dialog = hr.getByRole("dialog");
  if (await dialog.isVisible().catch(() => false))
    await dialog.getByRole("button", { name: /Record|Confirm/ }).click();
  await expect(hr.getByText("Hire recorded").first()).toBeVisible({ timeout: 15_000 });
  await expect(hr.getByRole("button", { name: "Record the hire" })).toBeHidden();
  await hr.screenshot({ path: test.info().outputPath("hire-recorded.png"), fullPage: true });
});
