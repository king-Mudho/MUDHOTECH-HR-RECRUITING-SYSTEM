"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, type ReactNode } from "react";

import { ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import { canEnter, type Area, useMe } from "../session";

/**
 * Client-side gate for authenticated areas. UI gating only - every API call is authorised by the
 * server; this just avoids rendering an area the user cannot use and handles signed-out sessions.
 */
export function AuthGate({ area, children }: { area: Area; children: ReactNode }) {
  const t = useTranslations("auth.gate");
  const { data: me, isPending, isError, error, refetch } = useMe();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isPending && !isError && me === null) {
      router.replace(`/login?next=${encodeURIComponent(pathname ?? "/")}`);
    }
  }, [isPending, isError, me, pathname, router]);

  if (isPending || me === null) return <PageSkeleton />;
  if (isError) {
    return (
      <div className="p-6">
        <ErrorState error={error} onRetry={() => refetch()} />
      </div>
    );
  }
  if (!canEnter(me, area)) {
    return (
      <div className="p-6">
        <ForbiddenState
          description={t("forbiddenBody")}
          action={
            <Button asChild className="min-h-10">
              <Link href="/">{t("goHome")}</Link>
            </Button>
          }
        />
      </div>
    );
  }
  return (
    <>
      {me.email_delivery_problem ? (
        <Alert role="status" className="rounded-none border-x-0 border-t-0">
          <AlertDescription>
            {t.rich("emailProblem", {
              email: me.email,
              link: (chunks) => (
                <Link href="/account/security" className="font-medium underline">
                  {chunks}
                </Link>
              ),
            })}
          </AlertDescription>
        </Alert>
      ) : null}
      {me.mfa.in_grace && area !== "account" ? (
        <Alert className="rounded-none border-x-0 border-t-0">
          <AlertDescription>
            {t.rich("mfaBanner", {
              date: me.mfa.grace_deadline
                ? new Date(me.mfa.grace_deadline).toLocaleDateString()
                : "",
              link: (chunks) => (
                <Link href="/account/security" className="font-medium underline">
                  {chunks}
                </Link>
              ),
            })}
          </AlertDescription>
        </Alert>
      ) : null}
      {children}
    </>
  );
}
