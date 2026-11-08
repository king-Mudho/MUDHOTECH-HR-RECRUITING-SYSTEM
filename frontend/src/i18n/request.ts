import { getRequestConfig } from "next-intl/server";

/**
 * Single-locale (en) configuration without i18n routing (ADR-017: English in MVP).
 * Shona (sn) and Ndebele (nd) message files are added in Phase 15.
 */
export const DEFAULT_LOCALE = "en";
export const DEFAULT_TIME_ZONE = "Africa/Harare";

export default getRequestConfig(async () => {
  const locale = DEFAULT_LOCALE;
  return {
    locale,
    timeZone: DEFAULT_TIME_ZONE,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
