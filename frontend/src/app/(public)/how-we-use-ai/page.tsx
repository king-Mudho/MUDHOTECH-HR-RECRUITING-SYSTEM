import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

/** Must match backend settings.AI_NOTICE_VERSION (stored with each candidate's consent record). */
const AI_NOTICE_VERSION = "2026-11-10";

const SECTIONS = ["does", "never", "choices"] as const;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("aiNotice");
  return {
    title: t("title"),
    description: t("description"),
    alternates: { canonical: "/how-we-use-ai" },
  };
}

export default async function HowWeUseAiPage() {
  const t = await getTranslations("aiNotice");
  return (
    <main
      id="main-content"
      className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-10"
    >
      <header>
        <h1 className="text-3xl font-bold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          {t("version", { version: AI_NOTICE_VERSION })}
        </p>
        <p className="mt-4 text-lg">{t("intro")}</p>
      </header>
      {SECTIONS.map((key) => (
        <section key={key} aria-labelledby={`ai-${key}`}>
          <h2 id={`ai-${key}`} className="text-xl font-semibold">
            {t(`sections.${key}.title`)}
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {(t.raw(`sections.${key}.items`) as string[]).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ))}
      <section aria-labelledby="ai-data">
        <h2 id="ai-data" className="text-xl font-semibold">
          {t("sections.data.title")}
        </h2>
        <p className="mt-2">{t("sections.data.body")}</p>
      </section>
      <p className="text-muted-foreground text-sm">{t("contact")}</p>
    </main>
  );
}
