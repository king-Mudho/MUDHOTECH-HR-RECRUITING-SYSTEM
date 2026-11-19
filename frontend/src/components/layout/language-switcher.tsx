"use client";

import { useLocale, useTranslations } from "next-intl";
import { useId, useTransition } from "react";

import { isLocale, LOCALE_COOKIE, LOCALE_LABELS, LOCALES, type Locale } from "@/i18n/locales";
import { api } from "@/lib/api-client";

/** Stores the choice in a cookie (read on the server) and on the account when signed in. */
export async function chooseLocale(locale: Locale): Promise<void> {
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; samesite=lax`;
  try {
    await api.patch("/me/", { locale });
  } catch {
    // not signed in: the cookie is enough
  }
}

export function LanguageSwitcher() {
  const t = useTranslations("language");
  const current = useLocale();
  const [pending, start] = useTransition();
  const id = useId();
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id} className="sr-only">
        {t("label")}
      </label>
      <select
        id={id}
        className="border-input bg-background h-9 rounded-md border px-2"
        value={current}
        disabled={pending}
        onChange={(e) => {
          const next = e.target.value;
          if (!isLocale(next)) return;
          start(async () => {
            await chooseLocale(next);
            window.location.reload(); // the boundary applies the new language on load
          });
        }}
      >
        {LOCALES.map((l) => (
          <option key={l} value={l} lang={l}>
            {LOCALE_LABELS[l]}
          </option>
        ))}
      </select>
      {current !== "en" ? <p className="text-xs">{t("draft")}</p> : null}
    </div>
  );
}
