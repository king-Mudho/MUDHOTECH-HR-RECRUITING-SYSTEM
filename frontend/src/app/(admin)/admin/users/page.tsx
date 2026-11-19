import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AdminUsers } from "@/features/admin/console";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("admin.console.users");
  return { title: t("title"), robots: { index: false } };
}

export default function Page() {
  return <AdminUsers />;
}
