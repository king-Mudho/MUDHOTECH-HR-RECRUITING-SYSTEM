"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMe } from "@/features/auth/session";

export function CandidateSettings() {
  const t = useTranslations("candidate.settings");
  const { data: me, isPending } = useMe();
  if (isPending || !me) return <PageSkeleton rows={2} />;
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("account")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <p>
            {t("email")}: <span className="font-medium">{me.email}</span>
          </p>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link href="/account/security">{t("security")}</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/candidate/profile">{t("profile")}</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("notifications")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-muted-foreground text-sm">
          {t("notificationsSoon")}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("privacy")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p>{t("privacyBody")}</p>
          <Link href="/how-we-use-ai" className="underline">
            {t("howWeUseAi")}
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
