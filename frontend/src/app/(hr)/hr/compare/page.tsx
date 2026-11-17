import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { CompareRoute } from "@/features/screening/compare";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("screening.compare");
  return { title: t("metaTitle") };
}

export default function ComparePage() {
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:p-6">
      <Suspense fallback={<PageSkeleton />}>
        <CompareRoute />
      </Suspense>
    </main>
  );
}
