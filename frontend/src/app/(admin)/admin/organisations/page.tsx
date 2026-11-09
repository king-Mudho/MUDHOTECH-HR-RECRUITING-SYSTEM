import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AdminOrganisations } from "@/features/admin/organisations";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("admin.organisations");
  return { title: t("title"), robots: { index: false } };
}

export default function Page() {
  return <AdminOrganisations />;
}
