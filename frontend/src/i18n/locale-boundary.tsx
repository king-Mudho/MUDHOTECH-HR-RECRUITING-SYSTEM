"use client";

import { NextIntlClientProvider, useMessages, type AbstractIntlMessages } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";

import { deepMerge, isLocale, LOCALE_COOKIE, type Locale } from "./locales";

function cookieLocale(): Locale {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${LOCALE_COOKIE}=`));
  const value = match?.split("=")[1];
  return isLocale(value) ? value : "en";
}

async function draft(locale: Locale): Promise<AbstractIntlMessages> {
  const mod =
    locale === "sn"
      ? await import("../../messages/sn.json")
      : await import("../../messages/nd.json");
  return mod.default as AbstractIntlMessages;
}

/**
 * Applies the language chosen with the switcher to client components (P15-T07). The first render
 * matches the English server HTML (no hydration mismatch); the translated messages follow. Keys the
 * machine-drafted catalogues lack stay English.
 */
export function LocaleBoundary({ children }: { children: ReactNode }) {
  const english = useMessages();
  const [state, setState] = useState<{ locale: Locale; messages: AbstractIntlMessages } | null>(
    null,
  );
  useEffect(() => {
    const locale = cookieLocale();
    if (locale === "en") return;
    let alive = true;
    void draft(locale).then((messages) => {
      if (!alive) return;
      document.documentElement.lang = locale;
      setState({ locale, messages: deepMerge(english, messages) });
    });
    return () => {
      alive = false;
    };
  }, [english]);
  if (!state) return <>{children}</>;
  return (
    <NextIntlClientProvider locale={state.locale} messages={state.messages}>
      {children}
    </NextIntlClientProvider>
  );
}
