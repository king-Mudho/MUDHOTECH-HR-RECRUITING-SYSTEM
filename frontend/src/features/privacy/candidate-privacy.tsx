"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";

import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

type RightsRequest = components["schemas"]["RightsRequest"];
type Consent = components["schemas"]["Consent"];
type Employer = components["schemas"]["Employer"];

const TYPES = [
  "access",
  "export",
  "correction",
  "deletion",
  "objection_automated",
  "consent_withdrawal",
] as const;

const keys = {
  requests: ["privacy", "requests"] as const,
  consents: ["privacy", "consents"] as const,
  employers: ["privacy", "employers"] as const,
};

function errorText(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : err ? fallback : null;
}

function Consents() {
  const t = useTranslations("privacy.consents");
  const tp = useTranslations("privacy.purposes");
  const format = useFormatter();
  const client = useQueryClient();
  const consents = useQuery({
    queryKey: keys.consents,
    queryFn: () => api.get<Consent[]>("/privacy/consents/"),
  });
  const withdraw = useMutation({
    mutationFn: (id: string) => api.post<Consent>(`/privacy/consents/${id}/withdraw/`),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.consents }),
  });
  return (
    <section aria-labelledby="consents" className="rounded-lg border p-4">
      <h2 id="consents" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-sm">{t("intro")}</p>
      {consents.isPending ? (
        <PageSkeleton rows={2} />
      ) : consents.isError ? (
        <ErrorState error={consents.error} onRetry={() => consents.refetch()} />
      ) : consents.data.length === 0 ? (
        <p className="text-muted-foreground mt-2 text-sm">{t("none")}</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2 text-sm">
          {consents.data.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-2 rounded-md border p-2">
              <span className="font-medium">{tp.has(c.purpose) ? tp(c.purpose) : c.purpose}</span>
              {c.organisation_name ? (
                <span className="text-muted-foreground">{c.organisation_name}</span>
              ) : null}
              <Badge variant="outline">
                {c.withdrawn_at
                  ? t("withdrawnOn", {
                      date: format.dateTime(new Date(c.withdrawn_at), { dateStyle: "medium" }),
                    })
                  : c.granted
                    ? t("given")
                    : t("notGiven")}
              </Badge>
              {c.granted && !c.withdrawn_at ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto"
                  disabled={withdraw.isPending}
                  onClick={() => withdraw.mutate(c.id)}
                >
                  {t("withdraw")}
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function NewRequest() {
  const t = useTranslations("privacy.new");
  const tt = useTranslations("privacy.types");
  const id = useId();
  const client = useQueryClient();
  const employers = useQuery({
    queryKey: keys.employers,
    queryFn: () => api.get<Employer[]>("/privacy/employers/"),
  });
  const [type, setType] = useState<(typeof TYPES)[number]>("access");
  const [scope, setScope] = useState("platform");
  const [details, setDetails] = useState("");
  const [password, setPassword] = useState("");
  const create = useMutation({
    mutationFn: () =>
      api.post<RightsRequest[]>("/privacy/requests/", {
        type,
        scope: scope.startsWith("org:") ? "organisation" : scope,
        organisation_id: scope.startsWith("org:") ? scope.slice(4) : null,
        details,
        password,
      }),
    onSuccess: () => {
      setPassword("");
      setDetails("");
      void client.invalidateQueries({ queryKey: keys.requests });
    },
  });
  return (
    <section aria-labelledby="new-request" className="rounded-lg border p-4">
      <h2 id="new-request" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-sm">{t("intro")}</p>
      <form
        className="mt-3 grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-type`}>{t("type")}</Label>
          <select
            id={`${id}-type`}
            className="border-input h-9 rounded-md border bg-transparent px-2 text-sm"
            value={type}
            onChange={(e) => setType(e.target.value as (typeof TYPES)[number])}
          >
            {TYPES.map((v) => (
              <option key={v} value={v}>
                {tt(v)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-scope`}>{t("scope")}</Label>
          <select
            id={`${id}-scope`}
            className="border-input h-9 rounded-md border bg-transparent px-2 text-sm"
            value={scope}
            onChange={(e) => setScope(e.target.value)}
          >
            <option value="platform">{t("scopePlatform")}</option>
            {(employers.data ?? []).map((e) => (
              <option key={e.id} value={`org:${e.id}`}>
                {e.name}
              </option>
            ))}
            {(employers.data ?? []).length ? <option value="all">{t("scopeAll")}</option> : null}
          </select>
        </div>
        <div className="flex flex-col gap-1 sm:col-span-2">
          <Label htmlFor={`${id}-details`}>
            {type === "correction" ? t("detailsCorrection") : t("details")}
          </Label>
          <textarea
            id={`${id}-details`}
            rows={3}
            className="border-input rounded-md border bg-transparent p-2 text-sm"
            value={details}
            onChange={(e) => setDetails(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-password`}>{t("password")}</Label>
          <Input
            id={`${id}-password`}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-describedby={`${id}-password-hint`}
          />
          <p id={`${id}-password-hint`} className="text-muted-foreground text-xs">
            {t("passwordHint")}
          </p>
        </div>
        <div className="flex items-end">
          <Button type="submit" disabled={create.isPending || !password}>
            {t("submit")}
          </Button>
        </div>
        {errorText(create.error, t("failed")) ? (
          <p role="alert" className="text-destructive text-sm sm:col-span-2">
            {errorText(create.error, t("failed"))}
          </p>
        ) : null}
        {create.isSuccess ? (
          <Alert className="sm:col-span-2" role="status">
            <AlertDescription>{t("checkEmail")}</AlertDescription>
          </Alert>
        ) : null}
      </form>
    </section>
  );
}

function Statement({ request }: { request: RightsRequest }) {
  const t = useTranslations("privacy.requests");
  const id = useId();
  const client = useQueryClient();
  const [text, setText] = useState("");
  const save = useMutation({
    mutationFn: () =>
      api.post<RightsRequest>(`/privacy/requests/${request.id}/statement/`, { statement: text }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.requests }),
  });
  if (request.statement)
    return <p className="text-xs">{t("yourStatement", { text: request.statement })}</p>;
  return (
    <form
      className="mt-2 flex flex-col gap-1"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <Label htmlFor={id}>{t("statementLabel")}</Label>
      <textarea
        id={id}
        rows={2}
        className="border-input rounded-md border bg-transparent p-2 text-sm"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <Button
        type="submit"
        size="sm"
        className="self-start"
        disabled={!text.trim() || save.isPending}
      >
        {t("addStatement")}
      </Button>
    </form>
  );
}

function MyRequests() {
  const t = useTranslations("privacy.requests");
  const tt = useTranslations("privacy.types");
  const ts = useTranslations("privacy.status");
  const format = useFormatter();
  const requests = useQuery({
    queryKey: keys.requests,
    queryFn: () => api.get<RightsRequest[]>("/privacy/requests/"),
  });
  return (
    <section aria-labelledby="my-requests" className="rounded-lg border p-4">
      <h2 id="my-requests" className="text-lg font-semibold">
        {t("title")}
      </h2>
      {requests.isPending ? (
        <PageSkeleton rows={2} />
      ) : requests.isError ? (
        <ErrorState error={requests.error} onRetry={() => requests.refetch()} />
      ) : requests.data.length === 0 ? (
        <p className="text-muted-foreground mt-2 text-sm">{t("none")}</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2 text-sm">
          {requests.data.map((r) => (
            <li key={r.id} className="rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{tt(r.type)}</span>
                <span className="text-muted-foreground">{r.organisation_name}</span>
                <Badge variant="outline">{ts(r.status)}</Badge>
                <span className="text-muted-foreground ml-auto font-mono text-xs">
                  {r.reference}
                </span>
              </div>
              <p className="text-muted-foreground mt-1 text-xs">
                {t("due", { date: format.dateTime(new Date(r.due_at), { dateStyle: "medium" }) })}
              </p>
              {r.resolution ? <p className="mt-1">{r.resolution}</p> : null}
              {r.type === "correction" && r.status === "declined" ? (
                <Statement request={r} />
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function CandidatePrivacy() {
  const t = useTranslations("privacy");
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <p className="text-muted-foreground text-sm">{t("intro")}</p>
      <Consents />
      <NewRequest />
      <MyRequests />
    </div>
  );
}

/** Landing page of the confirmation email link. */
export function ConfirmRequest() {
  const t = useTranslations("privacy.confirm");
  const token = useSearchParams().get("token") ?? "";
  const sent = useRef(false);
  const confirm = useMutation({
    mutationFn: () => api.post<RightsRequest[]>("/privacy/requests/confirm/", { token }),
  });
  useEffect(() => {
    if (token && !sent.current) {
      sent.current = true;
      confirm.mutate();
    }
  }, [token, confirm]);
  return (
    <div className="flex flex-col gap-3">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      {!token ? (
        <p role="alert">{t("missing")}</p>
      ) : confirm.isPending || confirm.isIdle ? (
        <p role="status">{t("working")}</p>
      ) : confirm.isError ? (
        <p role="alert" className="text-destructive">
          {errorText(confirm.error, t("failed"))}
        </p>
      ) : (
        <p role="status">{t("done", { count: confirm.data.length })}</p>
      )}
    </div>
  );
}
