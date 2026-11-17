import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { AuditLog } from "@/features/audit/audit-log";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("audit");
  return { title: t("title") };
}

export default function AuditPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <AuditLog />
    </Suspense>
  );
}
