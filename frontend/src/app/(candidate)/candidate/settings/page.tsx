import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { CandidateSettings } from "@/features/candidates/components/settings";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("candidate");
  return { title: t("settings.title"), robots: { index: false } };
}

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <CandidateSettings />
    </Suspense>
  );
}
