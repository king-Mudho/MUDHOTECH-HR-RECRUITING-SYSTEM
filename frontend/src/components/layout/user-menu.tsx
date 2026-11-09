"use client";

import { LogOut, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { homeFor, useLogout, useMe } from "@/features/auth/session";

/** Signed-in controls: account security link + sign out. Renders nothing when signed out. */
export function UserMenu({ showDashboard = false }: { showDashboard?: boolean }) {
  const t = useTranslations("nav");
  const { data: me } = useMe();
  const logout = useLogout();
  const router = useRouter();
  if (!me) return null;
  const onSignOut = async () => {
    await logout();
    router.replace("/");
    router.refresh();
  };
  return (
    <div className="flex items-center gap-1">
      {showDashboard ? (
        <Button asChild variant="ghost" className="min-h-10">
          <Link href={homeFor(me)}>{t("dashboard")}</Link>
        </Button>
      ) : null}
      <Button asChild variant="ghost" size="icon" className="size-10" aria-label={t("security")}>
        <Link href="/account/security">
          <ShieldCheck aria-hidden="true" />
        </Link>
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="size-10"
        aria-label={t("signOut")}
        onClick={onSignOut}
      >
        <LogOut aria-hidden="true" />
      </Button>
    </div>
  );
}
