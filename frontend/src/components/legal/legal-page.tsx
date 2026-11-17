import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

/** Namespaces in messages/en.json that hold a legal/statement page (title, intro, sections). */
export type LegalNamespace = "privacyNotice" | "termsPage" | "accessibilityStatement";

export async function legalMetadata(ns: LegalNamespace, path: string): Promise<Metadata> {
  const t = await getTranslations(ns);
  return { title: t("title"), description: t("description"), alternates: { canonical: path } };
}

/** Platform statement pages linked from the footer (P09: privacy notice, terms, accessibility). */
export async function LegalPage({ ns }: { ns: LegalNamespace }) {
  const t = await getTranslations(ns);
  const sections = t.raw("sections") as { title: string; items: string[] }[];
  return (
    <main
      id="main-content"
      className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-10"
    >
      <header>
        <h1 className="text-3xl font-bold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t("updated")}</p>
        <p className="mt-4 text-lg">{t("intro")}</p>
      </header>
      {sections.map((section, i) => (
        <section key={section.title} aria-labelledby={`${ns}-${i}`}>
          <h2 id={`${ns}-${i}`} className="text-xl font-semibold">
            {section.title}
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {section.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ))}
    </main>
  );
}
