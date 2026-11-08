import { getTranslations } from "next-intl/server";

export default async function DashboardPage() {
  const t = await getTranslations("areas");
  return (
    <main id="main-content" className="flex-1 p-6">
      <h1 className="text-2xl font-semibold">{t("hrTitle")}</h1>
      <p className="text-muted-foreground mt-2">{t("comingSoon")}</p>
    </main>
  );
}
