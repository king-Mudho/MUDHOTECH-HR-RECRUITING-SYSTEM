import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { JobsTable } from "@/features/jobs/components/jobs-table";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("jobs.list");
  return { title: t("title") };
}

export default function JobsPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <JobsTable />
    </Suspense>
  );
}
