"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

import { useMe } from "@/features/auth/session";

import { Brand } from "./brand";
import { UserMenu } from "./user-menu";

const LINKS = [
  { href: "/jobs", key: "jobs" },
  { href: "/employers", key: "employers" },
  { href: "/how-we-use-ai", key: "howWeUseAi" },
] as const;

export function PublicHeader() {
  const t = useTranslations("nav");
  const tc = useTranslations("common");
  const [open, setOpen] = useState(false);
  const { data: me } = useMe();
  return (
    <header className="bg-background/95 sticky top-0 z-30 border-b backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-4 px-4">
        <Brand />
        <nav aria-label={t("mainNavigation")} className="ml-6 hidden md:block">
          <ul className="flex items-center gap-1">
            {LINKS.map((l) => (
              <li key={l.href}>
                <Link
                  href={l.href}
                  className="text-muted-foreground hover:bg-muted hover:text-foreground inline-flex min-h-10 items-center rounded-md px-3 text-sm font-medium"
                >
                  {t(l.key)}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="ml-auto hidden items-center gap-2 md:flex">
          {me ? (
            <UserMenu showDashboard />
          ) : (
            <>
              <Button asChild variant="ghost" className="min-h-10">
                <Link href="/login">{t("login")}</Link>
              </Button>
              <Button asChild className="min-h-10">
                <Link href="/register">{t("register")}</Link>
              </Button>
            </>
          )}
        </div>
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="ml-auto size-10 md:hidden">
              <Menu aria-hidden="true" />
              <span className="sr-only">{tc("openMenu")}</span>
            </Button>
          </SheetTrigger>
          <SheetContent side="right" className="w-72">
            <SheetHeader>
              <SheetTitle>
                <Brand />
              </SheetTitle>
            </SheetHeader>
            <nav aria-label={t("mainNavigation")} className="px-4">
              <ul className="flex flex-col gap-1">
                {[
                  ...LINKS,
                  { href: "/login", key: "login" as const },
                  { href: "/register", key: "register" as const },
                ].map((l) => (
                  <li key={l.href}>
                    <Link
                      href={l.href}
                      onClick={() => setOpen(false)}
                      className="hover:bg-muted flex min-h-11 items-center rounded-md px-3 text-sm font-medium"
                    >
                      {t(l.key)}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          </SheetContent>
        </Sheet>
      </div>
    </header>
  );
}
