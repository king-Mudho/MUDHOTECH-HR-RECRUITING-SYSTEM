"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

const TABS = ["organisation", "structure", "team", "policies", "notifications"] as const;

export function SettingsNav() {
  const t = useTranslations("organisations.settings.nav");
  const pathname = usePathname() ?? "";
  return (
    <nav aria-label={t("label")} className="overflow-x-auto border-b">
      <ul className="flex gap-1">
        {TABS.map((tab) => {
          const href = `/hr/settings/${tab}`;
          const active = pathname.startsWith(href);
          return (
            <li key={tab}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex min-h-10 items-center border-b-2 px-3 text-sm font-medium whitespace-nowrap",
                  active
                    ? "border-primary text-foreground"
                    : "text-muted-foreground hover:text-foreground border-transparent",
                )}
              >
                {t(tab)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
