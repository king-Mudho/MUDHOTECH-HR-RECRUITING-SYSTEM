import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { ApplyWizardRoute } from "@/features/apply/wizard";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("apply");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default function ApplyPage() {
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <Suspense fallback={<PageSkeleton />}>
        <ApplyWizardRoute />
      </Suspense>
    </main>
  );
}
