"use client";

import {
  Activity,
  BarChart3,
  Briefcase,
  Building2,
  FileText,
  Flag,
  Inbox,
  LayoutDashboard,
  type LucideIcon,
  ScrollText,
  Settings,
  ShieldCheck,
  TriangleAlert,
  User,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

import type { NavIcon, NavItem } from "./nav-types";

const ICONS: Record<NavIcon, LucideIcon> = {
  dashboard: LayoutDashboard,
  jobs: Briefcase,
  applications: Inbox,
  profile: User,
  documents: FileText,
  settings: Settings,
  privacy: ShieldCheck,
  reports: BarChart3,
  organisations: Building2,
  users: Users,
  flags: Flag,
  health: Activity,
  deadLetters: TriangleAlert,
  audit: ScrollText,
};

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavList({
  items,
  labelKey,
  onNavigate,
  pathname,
}: {
  items: NavItem[];
  labelKey: string;
  onNavigate?: () => void;
  pathname: string;
}) {
  const t = useTranslations("nav");
  return (
    <nav aria-label={t(labelKey)}>
      <ul className="flex flex-col gap-1">
        {items.map((item) => {
          const Icon = item.icon ? ICONS[item.icon] : null;
          const active = isActive(pathname, item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
                  active
                    ? "bg-sidebar-primary text-sidebar-primary-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                )}
              >
                {Icon ? <Icon aria-hidden="true" className="size-4" /> : null}
                {t(item.labelKey)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function NavWithPath(props: { items: NavItem[]; labelKey: string; onNavigate?: () => void }) {
  return <NavList {...props} pathname={usePathname() ?? ""} />;
}

/**
 * Area navigation. The active-item highlight reads the URL, so it streams in under Suspense
 * (dynamic routes cannot know their pathname at prerender); the fallback is the same list
 * without a highlight.
 */
export function SidebarNav(props: { items: NavItem[]; labelKey: string; onNavigate?: () => void }) {
  return (
    <Suspense fallback={<NavList {...props} pathname="" />}>
      <NavWithPath {...props} />
    </Suspense>
  );
}
