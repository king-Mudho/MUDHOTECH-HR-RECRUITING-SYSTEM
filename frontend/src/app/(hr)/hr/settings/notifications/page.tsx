import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { NotificationTemplateSettings } from "@/features/notifications/template-editor";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("organisations.settings.nav");
  return { title: t("notifications") };
}

export default function Page() {
  return <NotificationTemplateSettings />;
}
