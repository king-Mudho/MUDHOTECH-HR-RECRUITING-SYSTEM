import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AiGovernance } from "@/features/ai-governance/ai-governance";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("aiGovernance");
  return { title: t("title"), robots: { index: false } };
}

export default function Page() {
  return <AiGovernance />;
}
