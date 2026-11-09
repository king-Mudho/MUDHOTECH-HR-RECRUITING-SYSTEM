import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { SettingsNav } from "@/features/organisations/components/settings-nav";

export default async function SettingsLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("organisations.settings");
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-4 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground">{t("subtitle")}</p>
      </div>
      <SettingsNav />
      {children}
    </main>
  );
}
