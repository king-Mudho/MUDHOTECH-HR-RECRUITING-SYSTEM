import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { ScreeningRoute } from "@/features/screening/screening-page";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("screening");
  return { title: t("metaTitle") };
}

export default function ScreeningPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <ScreeningRoute />
    </Suspense>
  );
}
