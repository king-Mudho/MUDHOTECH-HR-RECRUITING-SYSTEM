import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AdminSystem } from "@/features/admin/console";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("admin.console.system");
  return { title: t("title"), robots: { index: false } };
}

export default function Page() {
  return <AdminSystem />;
}
