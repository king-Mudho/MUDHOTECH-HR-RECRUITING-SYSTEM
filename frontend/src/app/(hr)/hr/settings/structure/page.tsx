import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { StructureSettings } from "@/features/organisations/components/settings";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("organisations.settings.nav");
  return { title: t("structure") };
}

export default function Page() {
  return <StructureSettings />;
}
