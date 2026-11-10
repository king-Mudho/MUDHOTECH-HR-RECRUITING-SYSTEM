import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { JobSearchForm } from "@/features/jobs/public/components";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("home");
  return {
    description: t("subtitle"),
    alternates: { canonical: "/" },
    openGraph: { title: t("title"), description: t("subtitle"), url: "/", type: "website" },
  };
}

export default async function HomePage() {
  const t = await getTranslations("home");
  return (
    <main
      id="main-content"
      className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-12"
    >
      <div>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t("title")}</h1>
        <p className="text-muted-foreground mt-3 max-w-2xl">{t("subtitle")}</p>
      </div>
      <section aria-label={t("searchLabel")} className="bg-muted/40 rounded-xl border p-4 sm:p-6">
        <JobSearchForm compact />
      </section>
      <p className="flex flex-wrap gap-x-6 gap-y-2">
        <Link href="/jobs" className="font-medium underline">
          {t("browseAll")}
        </Link>
        <Link href="/employers" className="underline">
          {t("employersCta")}
        </Link>
      </p>
    </main>
  );
}
