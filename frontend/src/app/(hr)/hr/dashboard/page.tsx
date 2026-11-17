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
    <Suspense fallback={<PageSkeleton />}>
      <HRDashboard />
    </Suspense>
  );
}
