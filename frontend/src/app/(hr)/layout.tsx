import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { UserMenu } from "@/components/layout/user-menu";
import { AuthGate } from "@/features/auth/components/auth-gate";
import { HR_NAV } from "@/components/layout/navigation";
import { NotificationBell, OrgSwitcher } from "@/components/layout/top-bar-actions";

export default async function HrLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("areas");
  return (
    <AppShell
      nav={HR_NAV}
      navLabelKey="hrNavigation"
      areaLabel={t("hrTitle")}
      homeHref="/hr/dashboard"
      topBarActions={
        <>
          <OrgSwitcher />
          <NotificationBell />
          <UserMenu />
        </>
      }
    >
      <AuthGate area="hr">{children}</AuthGate>
    </AppShell>
  );
}
