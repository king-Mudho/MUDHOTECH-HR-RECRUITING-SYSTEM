import { getTranslations } from "next-intl/server";
import { Suspense, type ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { UserMenu } from "@/components/layout/user-menu";
import { AuthGate } from "@/features/auth/components/auth-gate";
import { AreaMessages } from "@/i18n/client-messages";
import { CANDIDATE_NAV } from "@/components/layout/navigation";
import { NotificationBell } from "@/components/layout/top-bar-actions";

export default async function CandidateLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("areas");
  return (
    <AreaMessages>
      <AppShell
        nav={CANDIDATE_NAV}
        navLabelKey="candidateNavigation"
        areaLabel={t("candidateTitle")}
        homeHref="/candidate/dashboard"
        topBarActions={
          <>
            <NotificationBell />
            <UserMenu />
          </>
        }
      >
        <Suspense fallback={<PageSkeleton />}>
          <AuthGate area="candidate">{children}</AuthGate>
        </Suspense>
      </AppShell>
    </AreaMessages>
  );
}
