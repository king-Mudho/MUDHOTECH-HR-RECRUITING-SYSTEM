import { existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { ADMIN_NAV, CANDIDATE_NAV, HR_NAV } from "@/components/layout/navigation";

const APP = join(__dirname, "..", "src", "app");

/** Every route directory that holds a page.tsx, with route groups like "(hr)" removed. */
function routes(dir: string, prefix = ""): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (!statSync(path).isDirectory()) return [];
    const segment = name.startsWith("(") ? "" : `/${name}`;
    const here = existsSync(join(path, "page.tsx")) ? [`${prefix}${segment}`] : [];
    return [...here, ...routes(path, `${prefix}${segment}`)];
  });
}

describe("navigation", () => {
  it("only links to pages that exist", () => {
    const known = new Set(routes(APP));
    const missing = [...CANDIDATE_NAV, ...HR_NAV, ...ADMIN_NAV]
      .map((item) => item.href)
      .filter((href) => !known.has(href));
    expect(missing).toEqual([]);
  });
});
