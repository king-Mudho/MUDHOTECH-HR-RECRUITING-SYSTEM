"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { TextField } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { authApi } from "../allauth";
import { applyServerErrors } from "../form-errors";
import { reauthSchema, type ReauthValues } from "../schemas";

/** Sensitive account actions require a recent password confirmation (allauth "reauthenticate"). */
export function ReauthDialog({
  open,
  onOpenChange,
  onConfirmed,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirmed: () => void;
}) {
  const t = useTranslations("account.reauth");
  const tf = useTranslations("auth.fields");
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<ReauthValues>({
    resolver: zodResolver(reauthSchema),
    defaultValues: { password: "" },
  });
  const onSubmit = form.handleSubmit(async ({ password }) => {
    setFormError(null);
    try {
      await authApi.reauthenticate(password);
      form.reset();
      onOpenChange(false);
      onConfirmed();
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, { password: "password" }));
    }
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("body")}</DialogDescription>
        </DialogHeader>
        <form method="post" onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
          {formError ? (
            <p role="alert" className="text-destructive text-sm">
              {formError}
            </p>
          ) : null}
          <TextField
            label={tf("password")}
            type="password"
            autoComplete="current-password"
            autoFocus
            required
            error={form.formState.errors.password}
            {...form.register("password")}
          />
          <DialogFooter>
            <Button type="submit" className="min-h-10" disabled={form.formState.isSubmitting}>
              {t("confirm")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
