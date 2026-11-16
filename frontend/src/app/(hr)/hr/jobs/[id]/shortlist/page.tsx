import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { ShortlistRoute } from "@/features/shortlisting/builder";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("shortlisting");
  return { title: t("metaTitle") };
}

export default function ShortlistPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <ShortlistRoute />
    </Suspense>
  );
}
