import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { InvitationAccept } from "@/features/organisations/components/invitation-accept";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("organisations.invitation");
  return { title: t("pageTitle"), robots: { index: false } };
}

export default function InvitationPage() {
  return (
    <Suspense fallback={<PageSkeleton rows={3} />}>
      <InvitationAccept />
    </Suspense>
  );
}
