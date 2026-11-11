"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ErrorSummary, TextField } from "@/components/forms/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import { AllauthError, authApi, isAuthenticated, pendingFlow } from "../allauth";
import { applyServerErrors } from "../form-errors";
import { codeSchema, loginSchema, type CodeValues, type LoginValues } from "../schemas";
import { homeFor, reloadMe, safeNext } from "../session";
import { AuthCard } from "./auth-card";

type Step = "credentials" | "mfa" | "verify_email";

export function LoginForm() {
  const t = useTranslations("auth.login");
  const tf = useTranslations("auth.fields");
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("credentials");
  const [formError, setFormError] = useState<string | null>(null);

  const finish = async () => {
    const me = await reloadMe(queryClient);
    router.replace(safeNext(params.get("next")) ?? homeFor(me));
    router.refresh();
  };

  const credentials = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const mfa = useForm<CodeValues>({
    resolver: zodResolver(codeSchema),
    defaultValues: { code: "" },
  });

  const onCredentials = credentials.handleSubmit(async (values) => {
    setFormError(null);
    try {
      let resp;
      try {
        resp = await authApi.login(values.email, values.password);
      } catch (err) {
        // 409: this browser already has a session (e.g. another account). The person typed new
        // credentials, so end the old session and sign in once more.
        if (!(err instanceof AllauthError) || err.status !== 409) throw err;
        await authApi.logout().catch(() => undefined);
        queryClient.clear();
        resp = await authApi.login(values.email, values.password);
      }
      if (isAuthenticated(resp)) return finish();
      const flow = pendingFlow(resp);
      if (flow === "mfa_authenticate") setStep("mfa");
      else if (flow === "verify_email") setStep("verify_email");
      else setFormError(t("genericError"));
    } catch (err) {
      setFormError(applyServerErrors(err, credentials.setError) ?? t("genericError"));
    }
  });

  const onMfa = mfa.handleSubmit(async (values) => {
    setFormError(null);
    try {
      const resp = await authApi.mfaAuthenticate(values.code.replace(/\s+/g, ""));
      if (isAuthenticated(resp)) return finish();
      setFormError(t("genericError"));
    } catch (err) {
      setFormError(applyServerErrors(err, mfa.setError, { code: "code" }) ?? t("invalidCode"));
    }
  });

  if (step === "verify_email") {
    return (
      <AuthCard title={t("verifyTitle")} description={t("verifyBody")}>
        <Alert>
          <AlertDescription>{t("verifyHint")}</AlertDescription>
        </Alert>
        <Button variant="outline" className="min-h-10" onClick={() => setStep("credentials")}>
          {t("backToSignIn")}
        </Button>
      </AuthCard>
    );
  }

  if (step === "mfa") {
    return (
      <AuthCard title={t("mfaTitle")} description={t("mfaBody")}>
        <form method="post" onSubmit={onMfa} noValidate className="flex flex-col gap-4">
          <ErrorSummary
            errors={mfa.formState.errors}
            formError={formError}
            labels={{ code: tf("code") }}
            submitCount={mfa.formState.submitCount}
          />
          <TextField
            label={tf("code")}
            description={t("mfaCodeHelp")}
            inputMode="text"
            autoComplete="one-time-code"
            autoFocus
            required
            error={mfa.formState.errors.code}
            {...mfa.register("code")}
          />
          <Button type="submit" className="min-h-10" disabled={mfa.formState.isSubmitting}>
            {mfa.formState.isSubmitting ? t("verifying") : t("verify")}
          </Button>
        </form>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title={t("title")}
      description={t("subtitle")}
      footer={
        <p>
          {t("noAccount")}{" "}
          <Link href="/register" className="text-primary font-medium underline">
            {t("createAccount")}
          </Link>
        </p>
      }
    >
      <form method="post" onSubmit={onCredentials} noValidate className="flex flex-col gap-4">
        <ErrorSummary
          errors={credentials.formState.errors}
          formError={formError}
          labels={{ email: tf("email"), password: tf("password") }}
          submitCount={credentials.formState.submitCount}
        />
        <TextField
          label={tf("email")}
          type="email"
          autoComplete="email"
          required
          error={credentials.formState.errors.email}
          {...credentials.register("email")}
        />
        <TextField
          label={tf("password")}
          type="password"
          autoComplete="current-password"
          required
          error={credentials.formState.errors.password}
          {...credentials.register("password")}
        />
        <div className="flex justify-end">
          <Link href="/forgot-password" className="text-primary text-sm underline">
            {t("forgotPassword")}
          </Link>
        </div>
        <Button type="submit" className="min-h-10" disabled={credentials.formState.isSubmitting}>
          {credentials.formState.isSubmitting ? t("signingIn") : t("submit")}
        </Button>
      </form>
    </AuthCard>
  );
}
