"use client";

import { Menu } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

import { Brand } from "./brand";
import type { NavItem } from "./nav-types";
import { SidebarNav } from "./sidebar-nav";

/**
 * Authenticated area shell: persistent sidebar on desktop, slide-in sheet on mobile,
 * top bar with area-specific actions (org switcher, notifications, account).
 */
export function AppShell({
  nav,
  navLabelKey,
  areaLabel,
  homeHref,
  topBarActions,
  children,
}: {
  nav: NavItem[];
  navLabelKey: string;
  areaLabel: string;
  homeHref: string;
  topBarActions?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const t = useTranslations("common");
  return (
    <div className="flex min-h-full flex-1">
      <aside className="bg-sidebar hidden w-64 shrink-0 border-r lg:flex lg:flex-col">
        <div className="flex h-14 items-center border-b px-4">
          <Brand href={homeHref} />
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <p className="text-muted-foreground mb-2 px-3 text-xs font-semibold tracking-wide uppercase">
            {areaLabel}
          </p>
          <SidebarNav items={nav} labelKey={navLabelKey} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="bg-background/95 sticky top-0 z-30 flex h-14 items-center gap-2 border-b px-3 backdrop-blur sm:px-4">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="size-10 lg:hidden">
                <Menu aria-hidden="true" />
                <span className="sr-only">{t("openMenu")}</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="bg-sidebar w-72 p-0">
              <SheetHeader className="border-b px-4 py-3">
                <SheetTitle>
                  <Brand href={homeHref} />
                </SheetTitle>
              </SheetHeader>
              <div className="p-3">
                <SidebarNav items={nav} labelKey={navLabelKey} onNavigate={() => setOpen(false)} />
              </div>
            </SheetContent>
          </Sheet>
          <div className="lg:hidden">
            <Brand href={homeHref} />
          </div>
          <div className="ml-auto flex items-center gap-2">{topBarActions}</div>
        </header>
        <div className="flex flex-1 flex-col">{children}</div>
      </div>
    </div>
  );
}
