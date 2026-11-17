import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import messages from "../messages/en.json";

const APP = join(__dirname, "..", "src", "app", "(public)");

describe("platform statement pages", () => {
  it("every footer link has a page", () => {
    const footer = readFileSync(
      join(__dirname, "..", "src", "components", "layout", "public-footer.tsx"),
      "utf8",
    );
    const hrefs = [...footer.matchAll(/href="\/([a-z-]+)"/g)].map((m) => m[1]);
    expect(hrefs.length).toBeGreaterThan(0);
    expect(hrefs.filter((h) => !existsSync(join(APP, h, "page.tsx")))).toEqual([]);
  });

  it("EC-PRV-10: the privacy notice says backups expire within 35 days", () => {
    const retention = messages.privacyNotice.sections.find(
      (s) => s.title === "How long we keep it",
    );
    expect(retention?.items.some((i) => /backups/i.test(i) && i.includes("35 days"))).toBe(true);
  });

  it("EC-ORG-10: the privacy notice explains what happens when an employer closes", () => {
    const text = JSON.stringify(messages.privacyNotice);
    expect(text).toMatch(/employer closes its account/);
  });
});
