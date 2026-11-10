import type { Page } from "@playwright/test";

/**
 * Freeze CSS transitions/animations so axe checks the settled UI. Without this, axe can sample a
 * button mid-fade (e.g. disabled 50% opacity -> enabled) and report a contrast ratio no user sees.
 */
export async function settleForAxe(page: Page): Promise<void> {
  await page.addStyleTag({
    content: "*, *::before, *::after { transition: none !important; animation: none !important; }",
  });
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
}
