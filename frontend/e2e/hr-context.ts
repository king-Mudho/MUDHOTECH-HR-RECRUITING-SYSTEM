import type { Page } from "@playwright/test";

type Me = {
  active_organisation_id: string | null;
  memberships: { organisation_id: string; organisation_slug: string }[];
};

/**
 * The signed-in staff member's organisation and the demo "Software Developer" vacancy.
 * `active_organisation_id` is null until a user switches organisation, so fall back to the first
 * membership like the HR UI does (the nightly failed on this before).
 */
export async function hrContext(page: Page): Promise<{ org: string; job: string }> {
  const me = (await (await page.request.get("/api/v1/me/")).json()) as Me;
  const org = me.active_organisation_id ?? me.memberships[0]?.organisation_id;
  if (!org) throw new Error("The signed-in user has no organisation membership");
  const res = await page.request.get("/api/v1/hr/jobs/?search=Software%20Developer", {
    headers: { "X-Org-Id": org },
  });
  if (!res.ok()) throw new Error(`HR jobs lookup failed: ${res.status()} ${await res.text()}`);
  const jobs = (await res.json()) as { results: { id: string }[] };
  if (!jobs.results.length) throw new Error("No 'Software Developer' vacancy - run seed_demo");
  return { org, job: jobs.results[0].id };
}
