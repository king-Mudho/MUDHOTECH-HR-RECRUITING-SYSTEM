import { getRequestConfig } from "next-intl/server";

/**
 * Server rendering is English (ADR-017) so public pages stay statically prerendered (Cache
 * Components). The chosen language (Shona/Ndebele, P15-T07) is applied on the client by
 * ``LocaleBoundary`` after hydration, and to emails through the account's saved locale.
 */
export const DEFAULT_LOCALE = "en";
export const DEFAULT_TIME_ZONE = "Africa/Harare";

export default getRequestConfig(async () => ({
  locale: DEFAULT_LOCALE,
  timeZone: DEFAULT_TIME_ZONE,
  messages: (await import("../../messages/en.json")).default,
}));
