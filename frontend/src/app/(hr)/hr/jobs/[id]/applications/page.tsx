import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { JobApplicationsRoute } from "@/features/hr-applications/components";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("hrApplications");
  return { title: t("title") };
}

export default function JobApplicationsPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <JobApplicationsRoute />
    </Suspense>
  );
}
