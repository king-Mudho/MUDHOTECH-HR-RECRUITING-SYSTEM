import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { NotificationCentre } from "@/features/notifications/centre";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("notifications");
  return { title: t("title"), robots: { index: false } };
}

export default function NotificationsPage() {
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <Suspense fallback={<PageSkeleton />}>
        <NotificationCentre />
      </Suspense>
    </main>
  );
}
