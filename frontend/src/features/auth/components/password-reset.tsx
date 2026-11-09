"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ErrorSummary, TextField } from "@/components/forms/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import { AllauthError, authApi } from "../allauth";
import { applyServerErrors } from "../form-errors";
import {
  PASSWORD_MIN,
  forgotPasswordSchema,
  resetPasswordSchema,
  type ForgotPasswordValues,
  type ResetPasswordValues,
} from "../schemas";
import { AuthCard } from "./auth-card";

/** EC-ACC-06: identical response whether or not the address has an account. */
export function ForgotPasswordForm() {
  const t = useTranslations("auth.forgot");
  const tf = useTranslations("auth.fields");
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });
  const onSubmit = form.handleSubmit(async ({ email }) => {
    setFormError(null);
    try {
      await authApi.requestPasswordReset(email);
      setSent(true);
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, { email: "email" }));
    }
  });

  if (sent) {
    return (
      <AuthCard title={t("sentTitle")}>
        <Alert>
          <AlertDescription>{t("sentBody")}</AlertDescription>
        </Alert>
        <Button asChild variant="outline" className="min-h-10">
          <Link href="/login">{t("backToSignIn")}</Link>
        </Button>
      </AuthCard>
    );
  }
  return (
    <AuthCard title={t("title")} description={t("subtitle")}>
      <form method="post" onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <ErrorSummary
          errors={form.formState.errors}
          formError={formError}
          labels={{ email: tf("email") }}
          submitCount={form.formState.submitCount}
        />
        <TextField
          label={tf("email")}
          type="email"
          autoComplete="email"
          required
          error={form.formState.errors.email}
          {...form.register("email")}
        />
        <Button type="submit" className="min-h-10" disabled={form.formState.isSubmitting}>
          {t("submit")}
        </Button>
      </form>
    </AuthCard>
  );
}

export function ResetPasswordForm() {
  const t = useTranslations("auth.reset");
  const tf = useTranslations("auth.fields");
  const params = useSearchParams();
  const key = params.get("key") ?? "";
  const [done, setDone] = useState(false);
  const [expired, setExpired] = useState(!key);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "", confirmPassword: "" },
  });
  const onSubmit = form.handleSubmit(async ({ password }) => {
    setFormError(null);
    try {
      await authApi.resetPassword(key, password); // 200 or 401 (signed out) both mean success
      setDone(true);
    } catch (err) {
      if (err instanceof AllauthError && err.errors.some((e) => e.param === "key")) {
        setExpired(true);
        return;
      }
      setFormError(applyServerErrors(err, form.setError, { password: "password" }));
    }
  });

  if (expired) {
    return (
      <AuthCard title={t("expiredTitle")}>
        <Alert variant="destructive">
          <AlertDescription>{t("expiredBody")}</AlertDescription>
        </Alert>
        <Button asChild className="min-h-10">
          <Link href="/forgot-password">{t("requestNew")}</Link>
        </Button>
      </AuthCard>
    );
  }
  if (done) {
    return (
      <AuthCard title={t("doneTitle")}>
        <p role="status">{t("doneBody")}</p>
        <Button asChild className="min-h-10">
          <Link href="/login">{t("signIn")}</Link>
        </Button>
      </AuthCard>
    );
  }
  return (
    <AuthCard title={t("title")}>
      <form method="post" onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <ErrorSummary
          errors={form.formState.errors}
          formError={formError}
          labels={{ password: tf("newPassword"), confirmPassword: tf("confirmPassword") }}
          submitCount={form.formState.submitCount}
        />
        <TextField
          label={tf("newPassword")}
          type="password"
          autoComplete="new-password"
          required
          description={t("passwordHelp", { min: PASSWORD_MIN })}
          error={form.formState.errors.password}
          {...form.register("password")}
        />
        <TextField
          label={tf("confirmPassword")}
          type="password"
          autoComplete="new-password"
          required
          error={form.formState.errors.confirmPassword}
          {...form.register("confirmPassword")}
        />
        <Button type="submit" className="min-h-10" disabled={form.formState.isSubmitting}>
          {t("submit")}
        </Button>
      </form>
    </AuthCard>
  );
}
