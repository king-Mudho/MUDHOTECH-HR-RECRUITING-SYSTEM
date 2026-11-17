import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { PlatformSupportAccess } from "@/features/support/support-access";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("support");
  return { title: t("platformTitle"), robots: { index: false } };
}

export default function Page() {
  return (
    <main id="main-content" className="flex-1 p-6">
      <PlatformSupportAccess />
    </main>
  );
}
