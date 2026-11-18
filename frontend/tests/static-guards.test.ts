import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

import messages from "../messages/en.json";

/**
 * P10-T10 bug-bash guards: every literal translation key exists in messages/en.json (a missing
 * key renders as raw text) and every internal link points at a route that exists.
 */
const SRC = join(__dirname, "..", "src");
const APP = join(SRC, "app");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

function has(path: string): boolean {
  let node: unknown = messages;
  for (const part of path.split(".")) {
    if (!node || typeof node !== "object" || !(part in node)) return false;
    node = (node as Record<string, unknown>)[part];
  }
  return true;
}

const BIND =
  /(?:const|let)\s+(\w+)\s*=\s*(?:await\s+)?(?:useTranslations|getTranslations)\(\s*(?:["']([\w.]+)["'])?\s*\)/g;

describe("static guards", () => {
  it("uses only translation keys that exist", () => {
    const missing: string[] = [];
    let checked = 0;
    for (const file of files(SRC)) {
      const text = readFileSync(file, "utf8");
      const binds = [...text.matchAll(BIND)].map((m) => ({
        at: m.index ?? 0,
        name: m[1],
        ns: m[2] ?? "",
      }));
      for (const name of new Set(binds.map((b) => b.name))) {
        const call = new RegExp(
          `\\b${name}(?:\\.rich|\\.raw|\\.markup|\\.has)?\\(\\s*["']([\\w.]+)["']`,
          "g",
        );
        for (const m of text.matchAll(call)) {
          const before = binds.filter((b) => b.name === name && b.at < (m.index ?? 0)).at(-1);
          if (!before) continue;
          const key = before.ns ? `${before.ns}.${m[1]}` : m[1];
          checked += 1;
          if (!has(key)) missing.push(`${relative(SRC, file)}: ${key}`);
        }
      }
    }
    expect(checked).toBeGreaterThan(500);
    expect(missing).toEqual([]);
  });

  it("links only to routes that exist", () => {
    const routes = files(APP)
      .filter((f) => /[\\/](page\.tsx|route\.ts)$/.test(f))
      .map((f) =>
        relative(APP, join(f, ".."))
          .split(/[\\/]/)
          .filter((p) => p && !p.startsWith("(")),
      );
    const matches = (path: string) => {
      const segs = path.split("/").filter(Boolean);
      return routes.some((r) => {
        const catchAll = r.length > 0 && r[r.length - 1].startsWith("[...");
        if (!catchAll && r.length !== segs.length) return false;
        return r.every(
          (part, i) =>
            part.startsWith("[...") ||
            (i < segs.length && (part.startsWith("[") || part === segs[i] || segs[i] === "_")),
        );
      });
    };
    const link = /(?:href|push|replace|redirect)\s*[=(]\s*\{?\s*(["'`])(\/[^"'`]*)\1/g;
    const broken: string[] = [];
    let scanned = 0;
    for (const file of files(SRC)) {
      for (const m of readFileSync(file, "utf8").matchAll(link)) {
        const raw = m[2];
        if (raw.startsWith("/api/") || raw.startsWith("//")) continue;
        scanned += 1;
        const path = raw.replace(/\$\{[^}]*\}/g, "_").split(/[?#]/)[0];
        if (!matches(path)) broken.push(`${relative(SRC, file)}: ${raw}`);
      }
    }
    expect(scanned).toBeGreaterThan(50);
    expect(broken).toEqual([]);
  });
});
