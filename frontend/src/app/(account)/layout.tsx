import { getTranslations } from "next-intl/server";
import { Suspense, type ReactNode } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";

import { PublicHeader } from "@/components/layout/public-header";
import { AuthGate } from "@/features/auth/components/auth-gate";
import { AreaMessages } from "@/i18n/client-messages";

/** Account area shared by every signed-in user (candidates and staff). */
export default async function AccountLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations("apply");
  return (
    <AreaMessages>
      <div className="flex min-h-full flex-1 flex-col">
        <PublicHeader />
        {/* EC-APP-21: server-rendered, outside client components (no hydration mismatch). */}
        <noscript>
          <p className="bg-muted px-4 py-3 text-center text-sm">{t("needsJs")}</p>
        </noscript>
        <Suspense fallback={<PageSkeleton />}>
          <AuthGate area="account">{children}</AuthGate>
        </Suspense>
      </div>
    </AreaMessages>
  );
}
