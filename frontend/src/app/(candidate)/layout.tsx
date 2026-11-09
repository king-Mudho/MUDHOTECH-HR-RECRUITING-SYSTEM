import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { UserMenu } from "@/components/layout/user-menu";
import { AuthGate } from "@/features/auth/components/auth-gate";
import { CANDIDATE_NAV } from "@/components/layout/navigation";
import { NotificationBell } from "@/components/layout/top-bar-actions";

export default async function CandidateLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("areas");
  return (
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
      <AuthGate area="candidate">{children}</AuthGate>
    </AppShell>
  );
}
