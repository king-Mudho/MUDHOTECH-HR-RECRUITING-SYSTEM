import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { HRApplicationRoute } from "@/features/hr-applications/components";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("hrApplications");
  return { title: t("detail.pageTitle") };
}

export default function HRApplicationPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <HRApplicationRoute />
    </Suspense>
  );
}
