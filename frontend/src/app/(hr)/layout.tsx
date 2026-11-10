import { getTranslations } from "next-intl/server";
import { Suspense, type ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { UserMenu } from "@/components/layout/user-menu";
import { AuthGate } from "@/features/auth/components/auth-gate";
import { AreaMessages } from "@/i18n/client-messages";
import { HR_NAV } from "@/components/layout/navigation";
import { NotificationBell } from "@/components/layout/top-bar-actions";
import { OrgSwitcher } from "@/features/organisations/components/org-switcher";

export default async function HrLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("areas");
  return (
    <AreaMessages>
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
        <Suspense fallback={<PageSkeleton />}>
          <AuthGate area="hr">{children}</AuthGate>
        </Suspense>
      </AppShell>
    </AreaMessages>
  );
}
