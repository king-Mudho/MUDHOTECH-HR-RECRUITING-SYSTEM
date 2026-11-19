import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { BillingRoute } from "@/features/billing/components";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("billing");
  return { title: t("title") };
}

export default function BillingPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <BillingRoute />
    </Suspense>
  );
}
