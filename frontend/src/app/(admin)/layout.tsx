import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { ADMIN_NAV } from "@/components/layout/navigation";
import { NotificationBell } from "@/components/layout/top-bar-actions";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("areas");
  return (
    <AppShell
      nav={ADMIN_NAV}
      navLabelKey="adminNavigation"
      areaLabel={t("adminTitle")}
      homeHref="/admin/dashboard"
      topBarActions={<NotificationBell />}
    >
      {children}
    </AppShell>
  );
}
