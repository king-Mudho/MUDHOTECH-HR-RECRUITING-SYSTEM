import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { JobOverviewRoute } from "@/features/jobs/components/routes";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("jobs.overview");
  return { title: t("pageTitle") };
}

export default function JobOverviewPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <JobOverviewRoute />
    </Suspense>
  );
}
