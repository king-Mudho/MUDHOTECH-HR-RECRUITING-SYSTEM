import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { JobEditRoute } from "@/features/jobs/components/routes";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("jobs.wizard");
  return { title: t("editTitle") };
}

export default function EditJobPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <JobEditRoute />
    </Suspense>
  );
}
