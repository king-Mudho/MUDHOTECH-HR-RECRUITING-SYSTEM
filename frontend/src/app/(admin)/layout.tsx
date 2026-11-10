import { getTranslations } from "next-intl/server";
import { Suspense, type ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { UserMenu } from "@/components/layout/user-menu";
import { AuthGate } from "@/features/auth/components/auth-gate";
import { AreaMessages } from "@/i18n/client-messages";
import { ADMIN_NAV } from "@/components/layout/navigation";
import { NotificationBell } from "@/components/layout/top-bar-actions";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("areas");
  return (
    <AreaMessages>
      <AppShell
        nav={ADMIN_NAV}
        navLabelKey="adminNavigation"
        areaLabel={t("adminTitle")}
        homeHref="/admin/dashboard"
        topBarActions={
          <>
            <NotificationBell />
            <UserMenu />
          </>
        }
      >
        <Suspense fallback={<PageSkeleton />}>
          <AuthGate area="admin">{children}</AuthGate>
        </Suspense>
      </AppShell>
    </AreaMessages>
  );
}
