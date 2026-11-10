import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ApplyWizard } from "@/features/apply/wizard";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("apply");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default async function ApplyPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <ApplyWizard jobId={jobId} />
    </main>
  );
}
