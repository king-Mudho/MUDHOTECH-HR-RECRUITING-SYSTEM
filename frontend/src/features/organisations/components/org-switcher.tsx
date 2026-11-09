"use client";

import { Building2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { useActiveMembership, useSwitchOrganisation } from "../hooks";

/** FR-M02-05: switch between organisations (server stores the active org in the session). */
export function OrgSwitcher() {
  const t = useTranslations("nav");
  const tr = useTranslations("roles");
  const { membership, memberships } = useActiveMembership();
  const switchOrg = useSwitchOrganisation();
  if (!membership) return null;
  if (memberships.length === 1) {
    return (
      <span className="hidden items-center gap-2 text-sm font-medium sm:inline-flex">
        <Building2 aria-hidden="true" className="size-4" />
        <span className="max-w-48 truncate">{membership.organisation_name}</span>
        <span className="text-muted-foreground text-xs">· {tr(membership.role)}</span>
      </span>
    );
  }
  return (
    <label className="inline-flex items-center gap-2 text-sm">
      <Building2 aria-hidden="true" className="size-4" />
      <span className="sr-only">{t("switchOrganisation")}</span>
      <select
        value={membership.organisation_id}
        disabled={switchOrg.isPending}
        onChange={(e) => switchOrg.mutate(e.target.value)}
        className="border-input bg-background h-10 max-w-56 rounded-md border px-2"
      >
        {memberships.map((m) => (
          <option key={m.organisation_id} value={m.organisation_id}>
            {m.organisation_name} ({tr(m.role)})
          </option>
        ))}
      </select>
    </label>
  );
}
