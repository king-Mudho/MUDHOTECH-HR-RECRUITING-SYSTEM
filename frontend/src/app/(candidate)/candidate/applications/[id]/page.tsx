import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { CandidateApplicationDetailRoute } from "@/features/candidates/components/applications";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("candidate");
  return { title: t("applications.detailTitle"), robots: { index: false } };
}

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <CandidateApplicationDetailRoute />
    </Suspense>
  );
}
