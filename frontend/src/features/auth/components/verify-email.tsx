"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import { AllauthError, authApi, isAuthenticated } from "../allauth";
import { homeFor, reloadMe } from "../session";
import { AuthCard } from "./auth-card";

type State = "ready" | "working" | "done" | "invalid";

/**
 * Confirms an email verification key from the link. Verification needs an explicit click (mail
 * link scanners that pre-fetch pages must not confirm addresses). EC-ACC-04: used/expired links
 * get a friendly page with a way forward.
 */
export function VerifyEmail() {
  const t = useTranslations("auth.verify");
  const params = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const key = params.get("key") ?? "";
  const [state, setState] = useState<State>(key ? "ready" : "invalid");

  const confirm = async () => {
    setState("working");
    try {
      const resp = await authApi.verifyEmail(key);
      setState("done");
      if (isAuthenticated(resp)) {
        const me = await reloadMe(queryClient);
        router.replace(homeFor(me));
        router.refresh();
      }
    } catch (err) {
      setState(err instanceof AllauthError ? "invalid" : "ready");
    }
  };

  if (state === "invalid") {
    return (
      <AuthCard title={t("invalidTitle")}>
        <Alert variant="destructive">
          <AlertDescription>{t("invalidBody")}</AlertDescription>
        </Alert>
        <Button asChild className="min-h-10">
          <Link href="/login">{t("signInToResend")}</Link>
        </Button>
      </AuthCard>
    );
  }

  if (state === "done") {
    return (
      <AuthCard title={t("doneTitle")}>
        <p role="status">{t("doneBody")}</p>
        <Button asChild className="min-h-10">
          <Link href="/login">{t("continue")}</Link>
        </Button>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={t("title")} description={t("body")}>
      <Button onClick={confirm} className="min-h-10" disabled={state === "working"}>
        {state === "working" ? t("confirming") : t("confirm")}
      </Button>
    </AuthCard>
  );
}
