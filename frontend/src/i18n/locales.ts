/** Supported interface languages (P15-T07). Labels are in each language itself. */
export const LOCALES = ["en", "sn", "nd"] as const;
export type Locale = (typeof LOCALES)[number];

export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  sn: "chiShona",
  nd: "isiNdebele",
};

export const LOCALE_COOKIE = "NEXT_LOCALE";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

type Tree = { [key: string]: string | Tree };

/** ``base`` with every string ``override`` provides; keys it lacks keep the base (English). */
export function deepMerge<T extends object>(base: T, override: object): T {
  const out: Tree = { ...(base as Tree) };
  for (const [key, value] of Object.entries(override as Tree)) {
    if (key.startsWith("_")) continue; // metadata such as "_meta"
    const current = out[key];
    if (value && typeof value === "object" && current && typeof current === "object") {
      out[key] = deepMerge(current, value);
    } else if (typeof value === "string" && value.trim()) {
      out[key] = value;
    }
  }
  return out as T;
}
