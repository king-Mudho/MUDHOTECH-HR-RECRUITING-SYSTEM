import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * P09-T13: every signed-in page renders the skip-link target (`<main id="main-content">`) in the
 * page itself, an enclosing layout, or the feature component it renders.
 */
const APP = join(__dirname, "..", "src", "app");
const FEATURES = join(__dirname, "..", "src", "features");
const AREAS = ["(hr)", "(admin)", "(candidate)", "(account)"];

function pages(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return pages(path);
    return name === "page.tsx" ? [path] : [];
  });
}

function featureFiles(source: string): string[] {
  return [...source.matchAll(/from "@\/features\/([^"]+)"/g)].flatMap((m) =>
    [".tsx", ".ts", "/index.tsx"]
      .map((ext) => join(FEATURES, m[1] + ext))
      .filter((p) => existsSync(p)),
  );
}

function hasMain(page: string): boolean {
  const source = readFileSync(page, "utf8");
  if (source.includes("main-content")) return true;
  if (featureFiles(source).some((f) => readFileSync(f, "utf8").includes("main-content"))) {
    return true;
  }
  for (let dir = dirname(page); dir.startsWith(APP) && dir !== APP; dir = dirname(dir)) {
    const layout = join(dir, "layout.tsx");
    if (existsSync(layout) && readFileSync(layout, "utf8").includes("main-content")) return true;
  }
  return false;
}

describe("main landmark", () => {
  it("is present on every signed-in page", () => {
    const missing = AREAS.flatMap((area) => pages(join(APP, area)))
      .filter((p) => !hasMain(p))
      .map((p) => relative(APP, p));
    expect(missing).toEqual([]);
  });
});
