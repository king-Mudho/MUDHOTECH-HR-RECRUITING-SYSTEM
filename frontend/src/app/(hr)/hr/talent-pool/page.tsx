import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { TalentPoolRoute } from "@/features/talentpool/components";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("talentPool");
  return { title: t("title") };
}

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <TalentPoolRoute />
    </Suspense>
  );
}
