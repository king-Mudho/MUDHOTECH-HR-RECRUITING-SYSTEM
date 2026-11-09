import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { PolicySettings } from "@/features/organisations/components/settings";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("organisations.settings.nav");
  return { title: t("policies") };
}

export default function Page() {
  return <PolicySettings />;
}
