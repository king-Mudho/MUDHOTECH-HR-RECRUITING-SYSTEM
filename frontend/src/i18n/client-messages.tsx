import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import { getMessages } from "next-intl/server";
import type { ReactNode } from "react";

/**
 * Messages shipped to the browser. Public pages (job board, sign-in, invitations) only get the
 * namespaces their client components use, which keeps the HTML small on mobile data; the signed-in
 * areas wrap their tree in {@link AreaMessages} to get the full catalogue.
 * Server Components always have every message via `getTranslations`.
 */
export const PUBLIC_NAMESPACES = [
  "app",
  "common",
  "nav",
  "footer",
  "home",
  "areas",
  "states",
  "status",
  "validation",
  "forms",
  "auth",
  "roles",
  "organisations",
  "publicJobs",
] as const;

export function pickMessages(
  messages: AbstractIntlMessages,
  namespaces: readonly string[],
): AbstractIntlMessages {
  const out: AbstractIntlMessages = {};
  for (const ns of namespaces) if (ns in messages) out[ns] = messages[ns]!;
  return out;
}

export async function AreaMessages({ children }: { children: ReactNode }) {
  const messages = await getMessages();
  return <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>;
}
