import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { HRDashboard } from "@/features/dashboard/hr-dashboard";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("hrDashboard");
  return { title: t("title") };
}

export default function DashboardPage() {
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:p-6">
      <Suspense fallback={<PageSkeleton />}>
        <HRDashboard />
      </Suspense>
    </main>
  );
}
