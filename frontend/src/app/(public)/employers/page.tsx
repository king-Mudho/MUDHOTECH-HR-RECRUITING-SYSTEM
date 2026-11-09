import { CheckCircle2 } from "lucide-react";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { CreateOrganisation } from "@/features/organisations/components/create-organisation";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("organisations.employers");
  return { title: t("title"), description: t("subtitle") };
}

export default async function EmployersPage() {
  const t = await getTranslations("organisations.employers");
  const points = ["point1", "point2", "point3", "point4"] as const;
  return (
    <main
      id="main-content"
      className="mx-auto grid w-full max-w-6xl gap-10 px-4 py-10 lg:grid-cols-2"
    >
      <section aria-labelledby="employers-title" className="flex flex-col gap-4">
        <h1 id="employers-title" className="text-3xl font-bold tracking-tight">
          {t("title")}
        </h1>
        <p className="text-muted-foreground text-lg">{t("subtitle")}</p>
        <ul className="flex flex-col gap-3">
          {points.map((p) => (
            <li key={p} className="flex gap-3">
              <CheckCircle2 aria-hidden="true" className="text-success mt-0.5 size-5 shrink-0" />
              <span>{t(p)}</span>
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="create-org-title" className="flex flex-col gap-4">
        <h2 id="create-org-title" className="text-xl font-semibold">
          {t("formTitle")}
        </h2>
        <CreateOrganisation />
      </section>
    </main>
  );
}
