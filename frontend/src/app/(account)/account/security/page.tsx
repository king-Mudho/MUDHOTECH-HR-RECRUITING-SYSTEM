import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import {
  ChangeEmailCard,
  ChangePasswordCard,
  MfaCard,
  SessionsCard,
} from "@/features/auth/components/security-settings";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("account");
  return { title: t("title"), robots: { index: false } };
}

export default async function SecurityPage() {
  const t = await getTranslations("account");
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground">{t("subtitle")}</p>
      </div>
      <MfaCard />
      <ChangePasswordCard />
      <ChangeEmailCard />
      <SessionsCard />
    </main>
  );
}
