import Link from "next/link";
import { useTranslations } from "next-intl";

export function PublicFooter({ year }: { year: number }) {
  const t = useTranslations("footer");
  const ta = useTranslations("app");
  const tn = useTranslations("nav");
  return (
    <footer className="bg-muted/40 mt-auto border-t">
      <div className="text-muted-foreground mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-8 text-sm md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-foreground font-semibold">{ta("name")}</p>
          <p>{t("copyright", { year })}</p>
        </div>
        <nav aria-label={tn("footerNavigation")}>
          <ul className="flex flex-wrap gap-x-4 gap-y-2">
            <li>
              <Link className="inline-flex min-h-6 items-center hover:underline" href="/privacy">
                {t("privacy")}
              </Link>
            </li>
            <li>
              <Link className="inline-flex min-h-6 items-center hover:underline" href="/terms">
                {t("terms")}
              </Link>
            </li>
            <li>
              <Link
                className="inline-flex min-h-6 items-center hover:underline"
                href="/accessibility"
              >
                {t("accessibility")}
              </Link>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}
