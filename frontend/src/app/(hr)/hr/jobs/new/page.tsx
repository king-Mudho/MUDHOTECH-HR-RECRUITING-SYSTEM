import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { JobWizard } from "@/features/jobs/components/wizard";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("jobs.wizard");
  return { title: t("newTitle") };
}

export default function NewJobPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <JobWizard />
    </Suspense>
  );
}
