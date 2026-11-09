"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ErrorSummary, TextField } from "@/components/forms/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import { authApi } from "../allauth";
import { applyServerErrors } from "../form-errors";
import { PASSWORD_MIN, registerSchema, type RegisterValues } from "../schemas";
import { AuthCard } from "./auth-card";

export function RegisterForm() {
  const t = useTranslations("auth.register");
  const tf = useTranslations("auth.fields");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: "", password: "", confirmPassword: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      // 401 with a pending verify_email flow is the expected outcome (ADR-023) - and it is the
      // same whether or not the address already had an account (no enumeration).
      await authApi.signup(values.email, values.password);
      setSentTo(values.email.trim().toLowerCase());
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, { email: "email", password: "password" }));
    }
  });

  if (sentTo) {
    return (
      <AuthCard title={t("checkInboxTitle")}>
        <Alert>
          <AlertDescription>{t("checkInboxBody", { email: sentTo })}</AlertDescription>
        </Alert>
        <p className="text-muted-foreground text-sm">{t("checkInboxHint")}</p>
        <Button asChild variant="outline" className="min-h-10">
          <Link href="/login">{t("goToSignIn")}</Link>
        </Button>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title={t("title")}
      description={t("subtitle")}
      footer={
        <p>
          {t("haveAccount")}{" "}
          <Link href="/login" className="text-primary font-medium underline">
            {t("signIn")}
          </Link>
        </p>
      }
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <ErrorSummary
          errors={form.formState.errors}
          formError={formError}
          labels={{
            email: tf("email"),
            password: tf("password"),
            confirmPassword: tf("confirmPassword"),
            acceptTerms: t("terms"),
          }}
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
        <TextField
          label={tf("password")}
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
        <div className="flex items-start gap-2">
          <input
            id="field-acceptTerms"
            type="checkbox"
            className="mt-1 size-4"
            aria-invalid={form.formState.errors.acceptTerms ? true : undefined}
            {...form.register("acceptTerms")}
          />
          <label htmlFor="field-acceptTerms" className="text-sm">
            {t.rich("termsLabel", {
              terms: (chunks) => (
                <Link href="/terms" className="underline">
                  {chunks}
                </Link>
              ),
              privacy: (chunks) => (
                <Link href="/privacy" className="underline">
                  {chunks}
                </Link>
              ),
            })}
          </label>
        </div>
        <Button type="submit" className="min-h-10" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? t("creating") : t("submit")}
        </Button>
      </form>
    </AuthCard>
  );
}
