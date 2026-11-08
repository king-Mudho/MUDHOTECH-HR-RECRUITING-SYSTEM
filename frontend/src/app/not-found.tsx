import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Button } from "@/components/ui/button";

export default async function NotFound() {
  const t = await getTranslations("states");
  const tc = await getTranslations("common");
  return (
    <main
      id="main-content"
      className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-4 py-24 text-center"
    >
      <p className="text-primary text-sm font-semibold">404</p>
      <h1 className="text-3xl font-bold tracking-tight">{t("notFoundTitle")}</h1>
      <p className="text-muted-foreground">{t("notFoundBody")}</p>
      <Button asChild className="min-h-10">
        <Link href="/">{tc("goHome")}</Link>
      </Button>
    </main>
  );
}
