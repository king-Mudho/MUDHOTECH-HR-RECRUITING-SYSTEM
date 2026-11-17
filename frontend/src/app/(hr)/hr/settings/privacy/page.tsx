import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { HRPrivacy } from "@/features/privacy/hr-privacy";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("privacy.staff");
  return { title: t("title") };
}

export default function PrivacyPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <HRPrivacy />
    </Suspense>
  );
}
