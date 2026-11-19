import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { deepMerge, isLocale, LOCALES } from "@/i18n/locales";
import en from "../messages/en.json";
import nd from "../messages/nd.json";
import sn from "../messages/sn.json";

type Tree = { [k: string]: string | Tree };

function leaves(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([k, v]) =>
    typeof v === "string" ? [`${prefix}${k}`] : leaves(v, `${prefix}${k}.`),
  );
}

function has(tree: Tree, path: string): boolean {
  let node: string | Tree | undefined = tree;
  for (const part of path.split(".")) {
    if (!node || typeof node === "string") return false;
    node = node[part];
  }
  return typeof node === "string";
}

describe("locales", () => {
  it("supports en, sn and nd", () => {
    expect([...LOCALES]).toEqual(["en", "sn", "nd"]);
    expect(isLocale("sn")).toBe(true);
    expect(isLocale("fr")).toBe(false);
  });

  it("drafts only translate keys that exist in English and are marked for review", () => {
    for (const draft of [sn, nd] as Tree[]) {
      expect((draft._meta as Tree).status).toBe("machine-draft");
      const { _meta, ...rest } = draft;
      void _meta;
      const unknown = leaves(rest).filter((key) => !has(en as unknown as Tree, key));
      expect(unknown).toEqual([]);
    }
  });

  it("falls back to English for untranslated keys", () => {
    const merged = deepMerge(en, sn) as unknown as Tree;
    expect((merged.nav as Tree).jobs).toBe("Mabasa");
    expect((merged.nav as Tree).talentPool).toBe("Talent pool"); // not drafted yet
    expect("_meta" in merged).toBe(false);
  });

  it("keeps placeholders intact in the drafts", () => {
    const merged = deepMerge(en, nd) as unknown as Tree;
    expect((merged.common as Tree).requestId).toContain("{id}");
  });
});

describe("no hard-coded user-visible text", () => {
  const SRC = join(__dirname, "..", "src");
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) return files(path);
      return name.endsWith(".tsx") ? [path] : [];
    });
  // the global error page renders when the translation providers themselves failed
  const ALLOW = ["global-error.tsx"];

  it("JSX text and accessible labels come from the message catalogues", () => {
    const offenders: string[] = [];
    for (const file of files(SRC)) {
      if (ALLOW.some((a) => file.endsWith(a))) continue;
      const text = readFileSync(file, "utf8");
      for (const m of text.matchAll(/>\s*([A-Z][a-z]+(?: [a-zA-Z]+)+)\s*</g)) {
        offenders.push(`${file}: ${m[1]}`);
      }
      for (const m of text.matchAll(/(?:aria-label|placeholder|title|alt)="([A-Za-z][^"]{2,})"/g)) {
        if (!/^https?:\/\//.test(m[1]!)) offenders.push(`${file}: ${m[1]}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
