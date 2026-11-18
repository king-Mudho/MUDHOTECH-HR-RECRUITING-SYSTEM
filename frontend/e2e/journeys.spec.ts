/**
 * Phase 10 journeys (P10-T02) not covered by the other specs:
 * - a candidate asks for an export of their data, confirms it from the email and downloads it;
 * - a platform admin verifies a newly created organisation;
 * - screenshots of key pages for review and the user guides (`test-results/screens/`).
 *
 * Covered elsewhere: apply + withdraw (apply.spec), vacancy create -> approve -> publish (jobs.spec),
 * screening review, clarification and shortlist approval (core-scenario.spec), accessibility
 * (a11y-journeys.spec). Shortlist undo is covered by API and component tests
 * (apps/shortlisting/tests, tests/shortlist.test.tsx) because the core scenario's notification
 * window is consumed by its email assertions.
 *
 * Needs `seed_demo` + `seed_core_scenario` and DEMO_PASSWORD (nightly workflow).
 */
import path from "node:path";

import { expect, test } from "@playwright/test";

import {
  DEMO_PASSWORD,
  linkFromMail,
  open,
  pathOf,
  registerAndVerify,
  signIn,
  uniqueEmail,
} from "./helpers";

/** Screenshots for review and the user guides; uploaded by the nightly as the "screens" artifact. */
const screen = (name: string) => path.join(process.cwd(), "test-results", "screens", name);

const CANDIDATE = "candidate002@core-scenario.test";
const PLATFORM_ADMIN = "admin@mhrs-demo.test";

test.skip(!DEMO_PASSWORD, "DEMO_PASSWORD is required (seed_demo / seed_core_scenario accounts)");
test.describe.configure({ mode: "serial", timeout: 4 * 60_000 });

test("candidate exports their data after confirming by email", async ({ page, request }, info) => {
  // one project only: both would share the candidate's mailbox and requests
  test.skip(info.project.name !== "chromium", "runs once");
  await signIn(page, CANDIDATE, DEMO_PASSWORD, "/candidate/privacy");
  await expect(page.getByRole("heading", { name: "Privacy and your data" })).toBeVisible();
  await page.getByLabel("What would you like?").selectOption("export");
  await page.getByLabel("Who should handle it?").selectOption("platform");
  await page.getByLabel("Your password").fill(DEMO_PASSWORD);
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByText(/Request recorded/)).toBeVisible();

  const link = await linkFromMail(
    request,
    CANDIDATE,
    /https?:\/\/[^\s]+\/candidate\/privacy\/confirm\?token=[\w-]+/,
  );
  await open(page, pathOf(link));
  await expect(page.getByText(/request is confirmed/)).toBeVisible({ timeout: 20_000 });

  // the bundle is built by the reports worker; the download appears on the privacy page
  await expect
    .poll(
      async () => {
        await open(page, "/candidate/privacy");
        return page.getByRole("button", { name: "Download my data" }).count();
      },
      { timeout: 2 * 60_000, intervals: [5_000] },
    )
    .toBeGreaterThan(0);
  await page.screenshot({
    path: screen("candidate-privacy.png"),
    fullPage: true,
  });
});

test("platform admin verifies a new organisation", async ({ browser, request }, info) => {
  test.skip(info.project.name !== "chromium", "runs once");
  const owner = await (await browser.newContext()).newPage();
  const name = `E2E Verify Ltd ${Date.now()}`;
  await registerAndVerify(owner, request, uniqueEmail("owner"));
  await open(owner, "/employers");
  await owner.getByLabel(/^Organisation name/).fill(name);
  await owner.getByLabel(/^City or town/).fill("Mutare");
  await owner.getByRole("button", { name: "Create organisation" }).click();
  await expect(owner.getByText(/awaiting verification/)).toBeVisible({ timeout: 20_000 });

  const admin = await (await browser.newContext()).newPage();
  await signIn(admin, PLATFORM_ADMIN, DEMO_PASSWORD, "/admin/organisations");
  await admin.getByLabel("Search by name or registration number").fill(name);
  const row = admin.getByRole("row").filter({ hasText: name });
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.getByRole("button", { name: "Verify" }).click();
  const dialog = admin.getByRole("dialog");
  await dialog.getByRole("button", { name: "Verify" }).click();
  await expect(row.getByText("Active")).toBeVisible({ timeout: 20_000 });
  await admin.screenshot({ path: screen("admin-organisations.png") });
});

test("key pages render for screenshots", async ({ page }, info) => {
  for (const [path, file] of [
    ["/", "home"],
    ["/jobs", "job-board"],
    ["/how-we-use-ai", "how-we-use-ai"],
    ["/privacy", "privacy-notice"],
  ] as const) {
    await open(page, path);
    await expect(page.locator("main").first()).toBeVisible();
    await page.screenshot({
      path: screen(`${info.project.name}-${file}.png`),
      fullPage: true,
    });
  }
});
