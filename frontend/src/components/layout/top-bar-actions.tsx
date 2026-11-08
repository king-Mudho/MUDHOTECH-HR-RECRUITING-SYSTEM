"use client";

import { Bell, Building2, ChevronsUpDown } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";

/** Placeholder org switcher - wired to memberships in Phase 02 (P02-T13). */
export function OrgSwitcher({ orgName }: { orgName?: string }) {
  const t = useTranslations("nav");
  return (
    <Button variant="outline" className="min-h-10 gap-2" aria-label={t("switchOrganisation")}>
      <Building2 aria-hidden="true" />
      <span className="max-w-40 truncate">{orgName ?? t("organisation")}</span>
      <ChevronsUpDown aria-hidden="true" className="opacity-60" />
    </Button>
  );
}

/** Placeholder bell - unread count + polling arrive in Phase 05 (P05-T05). */
export function NotificationBell({ unread = 0 }: { unread?: number }) {
  const t = useTranslations("nav");
  return (
    <Button
      variant="ghost"
      size="icon"
      className="relative size-10"
      aria-label={t("notifications")}
    >
      <Bell aria-hidden="true" />
      {unread > 0 ? (
        <span className="bg-destructive absolute top-1.5 right-1.5 grid min-w-4 place-items-center rounded-full px-1 text-[10px] leading-4 font-semibold text-white">
          {unread > 99 ? "99+" : unread}
          <span className="sr-only"> unread</span>
        </span>
      ) : null}
    </Button>
  );
}
