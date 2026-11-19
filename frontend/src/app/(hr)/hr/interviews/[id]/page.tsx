import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { InterviewDetailRoute } from "@/features/interviews/components";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("interviews");
  return { title: t("metaTitle") };
}

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <InterviewDetailRoute />
    </Suspense>
  );
}
