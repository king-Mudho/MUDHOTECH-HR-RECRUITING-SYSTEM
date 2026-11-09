"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import QRCode from "qrcode";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { TextField } from "@/components/forms/form-field";
import { ErrorState } from "@/components/states/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

import { authApi, pendingFlow } from "../allauth";
import { applyServerErrors } from "../form-errors";
import {
  PASSWORD_MIN,
  changeEmailSchema,
  changePasswordSchema,
  codeSchema,
  type ChangeEmailValues,
  type ChangePasswordValues,
  type CodeValues,
} from "../schemas";
import { useMe, useRefreshMe } from "../session";
import { ReauthDialog } from "./reauth-dialog";

type UserSession = components["schemas"]["UserSession"];

/**
 * allauth answers sensitive account actions with a pending "reauthenticate" flow when the last
 * password entry is too old. `requireReauth(action)` asks for the password, then re-runs `action`.
 */
function useReauthGuard() {
  const [retry, setRetry] = useState<null | (() => void)>(null);
  const requireReauth = (action: () => void) => setRetry(() => action);
  const dialog = (
    <ReauthDialog
      open={retry !== null}
      onOpenChange={(open) => !open && setRetry(null)}
      onConfirmed={() => {
        const action = retry;
        setRetry(null);
        action?.();
      }}
    />
  );
  return { requireReauth, dialog };
}

export function ChangePasswordCard() {
  const t = useTranslations("account.password");
  const tf = useTranslations("auth.fields");
  const [status, setStatus] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
  });
  const onSubmit = form.handleSubmit(async (v) => {
    setStatus(null);
    setFormError(null);
    try {
      await authApi.changePassword(v.currentPassword, v.newPassword);
      form.reset();
      setStatus(t("changed"));
    } catch (err) {
      setFormError(
        applyServerErrors(err, form.setError, {
          current_password: "currentPassword",
          new_password: "newPassword",
        }),
      );
    }
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate className="flex max-w-md flex-col gap-4">
          {formError ? (
            <p role="alert" className="text-destructive text-sm">
              {formError}
            </p>
          ) : null}
          {status ? (
            <p role="status" className="text-success text-sm">
              {status}
            </p>
          ) : null}
          <TextField
            label={tf("currentPassword")}
            type="password"
            autoComplete="current-password"
            required
            error={form.formState.errors.currentPassword}
            {...form.register("currentPassword")}
          />
          <TextField
            label={tf("newPassword")}
            type="password"
            autoComplete="new-password"
            required
            description={t("help", { min: PASSWORD_MIN })}
            error={form.formState.errors.newPassword}
            {...form.register("newPassword")}
          />
          <TextField
            label={tf("confirmPassword")}
            type="password"
            autoComplete="new-password"
            required
            error={form.formState.errors.confirmPassword}
            {...form.register("confirmPassword")}
          />
          <Button
            type="submit"
            className="min-h-10 self-start"
            disabled={form.formState.isSubmitting}
          >
            {t("submit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function ChangeEmailCard() {
  const t = useTranslations("account.email");
  const tf = useTranslations("auth.fields");
  const { data: me } = useMe();
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<ChangeEmailValues>({
    resolver: zodResolver(changeEmailSchema),
    defaultValues: { email: "" },
  });
  const onSubmit = form.handleSubmit(async ({ email }) => {
    setFormError(null);
    try {
      await authApi.changeEmail(email);
      setSentTo(email);
      form.reset();
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, { email: "email" }));
    }
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
        </CardTitle>
        <CardDescription>{t("current", { email: me?.email ?? "…" })}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate className="flex max-w-md flex-col gap-4">
          {formError ? (
            <p role="alert" className="text-destructive text-sm">
              {formError}
            </p>
          ) : null}
          {sentTo ? (
            <p role="status" className="text-sm">
              {t("sent", { email: sentTo })}
            </p>
          ) : null}
          <TextField
            label={tf("newEmail")}
            type="email"
            autoComplete="email"
            required
            description={t("help")}
            error={form.formState.errors.email}
            {...form.register("email")}
          />
          <Button
            type="submit"
            className="min-h-10 self-start"
            disabled={form.formState.isSubmitting}
          >
            {t("submit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function MfaCard() {
  const t = useTranslations("account.mfa");
  const tf = useTranslations("auth.fields");
  const { data: me } = useMe();
  const refreshMe = useRefreshMe();
  const { requireReauth, dialog } = useReauthGuard();
  const [setup, setSetup] = useState<{ secret: string; qr: string } | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<CodeValues>({
    resolver: zodResolver(codeSchema),
    defaultValues: { code: "" },
  });

  const startSetup = async (): Promise<void> => {
    setFormError(null);
    const resp = await authApi.totpStatus();
    if (pendingFlow(resp) === "reauthenticate") return requireReauth(() => void startSetup());
    const meta = resp.meta as { secret?: string; totp_url?: string } | undefined;
    if (meta?.secret && meta.totp_url) {
      setSetup({ secret: meta.secret, qr: await QRCode.toDataURL(meta.totp_url, { margin: 1 }) });
    }
  };

  const showCodes = async (): Promise<void> => {
    const resp = await authApi.recoveryCodes();
    if (pendingFlow(resp) === "reauthenticate") return requireReauth(() => void showCodes());
    if (resp.data?.unused_codes) setCodes(resp.data.unused_codes);
  };

  const onActivate = form.handleSubmit(async ({ code }) => {
    setFormError(null);
    try {
      await authApi.activateTotp(code.replace(/\s+/g, ""));
      setSetup(null);
      form.reset();
      await refreshMe();
      await showCodes();
    } catch (err) {
      setFormError(applyServerErrors(err, form.setError, { code: "code" }));
    }
  });

  const status = me?.mfa;
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {status?.required && !status.enabled ? (
          <Alert variant={status.enforced ? "destructive" : "default"}>
            <AlertTitle>{t("requiredTitle")}</AlertTitle>
            <AlertDescription>
              {status.enforced
                ? t("enforcedBody")
                : t("graceBody", {
                    date: status.grace_deadline
                      ? new Date(status.grace_deadline).toLocaleDateString()
                      : "",
                  })}
            </AlertDescription>
          </Alert>
        ) : null}

        {status?.enabled ? (
          <div className="flex flex-col gap-3">
            <p role="status" className="text-success font-medium">
              {t("enabled")}
            </p>
            <Button variant="outline" className="min-h-10 self-start" onClick={showCodes}>
              {t("showCodes")}
            </Button>
          </div>
        ) : setup ? (
          <form onSubmit={onActivate} noValidate className="flex max-w-md flex-col gap-4">
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              <li>{t("step1")}</li>
              <li>{t("step2")}</li>
            </ol>
            {/* eslint-disable-next-line @next/next/no-img-element -- data: URL generated locally */}
            <img
              src={setup.qr}
              alt={t("qrAlt")}
              width={192}
              height={192}
              className="rounded border"
            />
            <p className="text-sm">
              {t("manualKey")}{" "}
              <code className="bg-muted rounded px-1 break-all">{setup.secret}</code>
            </p>
            {formError ? (
              <p role="alert" className="text-destructive text-sm">
                {formError}
              </p>
            ) : null}
            <TextField
              label={tf("code")}
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              error={form.formState.errors.code}
              {...form.register("code")}
            />
            <Button
              type="submit"
              className="min-h-10 self-start"
              disabled={form.formState.isSubmitting}
            >
              {t("activate")}
            </Button>
          </form>
        ) : (
          <Button className="min-h-10 self-start" onClick={startSetup}>
            {t("setUp")}
          </Button>
        )}

        {codes ? (
          <Alert>
            <AlertTitle>{t("codesTitle")}</AlertTitle>
            <AlertDescription>
              <p className="mb-2">{t("codesBody")}</p>
              <ul className="grid grid-cols-2 gap-1 font-mono text-sm" aria-label={t("codesTitle")}>
                {codes.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ) : null}
        {dialog}
      </CardContent>
    </Card>
  );
}

export function SessionsCard() {
  const t = useTranslations("account.sessions");
  const queryClient = useQueryClient();
  const sessions = useQuery({
    queryKey: ["account", "sessions"],
    queryFn: () => api.get<UserSession[]>("/me/sessions/"),
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["account", "sessions"] });
  const revoke = useMutation({
    mutationFn: (id: number) => api.delete<void>(`/me/sessions/${id}/`),
    onSuccess: invalidate,
  });
  const revokeOthers = useMutation({
    mutationFn: () => api.post<{ revoked: number }>("/me/sessions/revoke-others/"),
    onSuccess: invalidate,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {sessions.isPending ? (
          <div className="flex flex-col gap-2" role="status" aria-label={t("loading")}>
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : sessions.isError ? (
          <ErrorState error={sessions.error} onRetry={() => sessions.refetch()} />
        ) : (
          <ul className="divide-y rounded-md border">
            {sessions.data.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {s.user_agent || t("unknownDevice")}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {t("meta", { ip: s.ip, lastSeen: new Date(s.last_seen_at).toLocaleString() })}
                  </p>
                </div>
                {s.is_current ? (
                  <span className="text-success text-xs font-semibold">{t("thisDevice")}</span>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    className="min-h-8"
                    onClick={() => revoke.mutate(s.id)}
                    disabled={revoke.isPending}
                  >
                    {t("revoke")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        <Button
          variant="outline"
          className="min-h-10 self-start"
          onClick={() => revokeOthers.mutate()}
          disabled={revokeOthers.isPending || (sessions.data?.length ?? 0) < 2}
        >
          {t("revokeOthers")}
        </Button>
        {revokeOthers.data ? (
          <p role="status" className="text-sm">
            {t("revokedCount", { count: revokeOthers.data.revoked })}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
