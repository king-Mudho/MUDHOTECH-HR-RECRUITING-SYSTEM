"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";

import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ALLAUTH_BASE } from "@/features/auth/allauth";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api, getCookie } from "@/lib/api-client";
import type { components } from "@/types/api";

type S = components["schemas"];
type Overview = S["IntegrationsOverview"];
type Provider = S["Provider"];
type Connection = S["Connection"];
type Webhooks = S["WebhooksOverview"];
type ApiKey = S["ApiKey"];

const errText = (err: unknown, fallback: string) =>
  err ? (err instanceof ApiError ? err.message : fallback) : null;

function useOrgQuery<T>(key: string, path: string, enabled = true) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: ["integrations", orgId ?? "", key],
    queryFn: () => api.get<T>(path, { orgId: orgId! }),
    enabled: !!orgId && enabled,
  });
}

// --- connections --------------------------------------------------------------------------------
function ConnectForm({ provider, sandbox }: { provider: Provider; sandbox: boolean }) {
  const t = useTranslations("integrations");
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const prefix = useId();
  const connect = useMutation({
    mutationFn: () => {
      const pick = (keys: string[]) => Object.fromEntries(keys.map((k) => [k, values[k] ?? ""]));
      return api.post<Connection>(
        "/hr/integrations/",
        {
          provider: provider.key,
          credentials: pick(provider.credential_fields),
          config: pick(provider.config_fields),
          sandbox,
        },
        { orgId: orgId! },
      );
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["integrations", orgId ?? ""] }),
  });
  const fields = [...provider.credential_fields, ...provider.config_fields];
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        connect.mutate();
      }}
    >
      {fields.map((f) => (
        <div key={f} className="flex flex-col gap-1">
          <Label htmlFor={`${prefix}-${f}`}>{t.has(`fields.${f}`) ? t(`fields.${f}`) : f}</Label>
          <Input
            id={`${prefix}-${f}`}
            className="h-9 w-56"
            type={provider.credential_fields.includes(f) ? "password" : "text"}
            autoComplete="off"
            value={values[f] ?? ""}
            onChange={(e) => setValues((v) => ({ ...v, [f]: e.target.value }))}
          />
        </div>
      ))}
      <Button size="sm" type="submit" disabled={connect.isPending}>
        {t("connect")}
      </Button>
      {connect.error ? (
        <span role="alert" className="text-destructive text-sm">
          {errText(connect.error, t("failed"))}
        </span>
      ) : null}
    </form>
  );
}

function ConnectionRow({ c }: { c: Connection }) {
  const t = useTranslations("integrations");
  const format = useFormatter();
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ["integrations", orgId ?? ""] });
  const test = useMutation({
    mutationFn: () => api.post<Connection>(`/hr/integrations/${c.id}/test/`, {}, { orgId: orgId! }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/hr/integrations/${c.id}/`, { orgId: orgId! }),
    onSuccess: refresh,
  });
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge variant={c.status === "active" ? "outline" : "destructive"}>
        {t(`status.${c.status}`)}
      </Badge>
      {c.sandbox ? <Badge variant="secondary">{t("sandbox")}</Badge> : null}
      <span className="text-muted-foreground">
        {t("credentials", { hint: c.credentials_hint })}
      </span>
      {c.last_success_at ? (
        <span className="text-muted-foreground">
          {t("lastOk", {
            date: format.dateTime(new Date(c.last_success_at), {
              dateStyle: "medium",
              timeStyle: "short",
            }),
          })}
        </span>
      ) : null}
      {c.last_error ? <span className="text-destructive">{c.last_error}</span> : null}
      <span className="ml-auto flex gap-2">
        <Button size="sm" variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
          {t("test")}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
        >
          {t("disconnect")}
        </Button>
      </span>
    </div>
  );
}

function Connections() {
  const t = useTranslations("integrations");
  const q = useOrgQuery<Overview>("overview", "/hr/integrations/");
  if (q.isPending) return <PageSkeleton rows={2} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <section aria-labelledby="connections" className="flex flex-col gap-3 rounded-lg border p-4">
      <h2 id="connections" className="text-lg font-semibold">
        {t("title")}
      </h2>
      {q.data.sandbox_default ? <p className="text-sm">{t("sandboxNote")}</p> : null}
      <ul className="flex flex-col gap-3">
        {q.data.providers.map((p) => {
          const conn = q.data.connections.find((c) => c.provider === p.key);
          return (
            <li key={p.key} className="flex flex-col gap-2 rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{p.name}</span>
                <Badge variant="outline">{p.per_user ? t("personal") : t("organisation")}</Badge>
              </div>
              {conn ? (
                <ConnectionRow c={conn} />
              ) : (
                <ConnectForm provider={p} sandbox={q.data.sandbox_default} />
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// --- webhooks -----------------------------------------------------------------------------------
function WebhooksSection() {
  const t = useTranslations("integrations.webhooks");
  const format = useFormatter();
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const q = useOrgQuery<Webhooks>("webhooks", "/hr/webhooks/");
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [secret, setSecret] = useState<string | null>(null);
  const urlId = useId();
  const refresh = () =>
    client.invalidateQueries({ queryKey: ["integrations", orgId ?? "", "webhooks"] });
  const create = useMutation({
    mutationFn: () =>
      api.post<{ secret: string }>("/hr/webhooks/", { url, events }, { orgId: orgId! }),
    onSuccess: async (res) => {
      setSecret(res.secret);
      setUrl("");
      setEvents([]);
      await refresh();
    },
  });
  const replay = useMutation({
    mutationFn: (id: string) =>
      api.post(`/hr/webhooks/deliveries/${id}/replay/`, {}, { orgId: orgId! }),
    onSuccess: refresh,
  });
  if (q.isPending) return <PageSkeleton rows={2} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <section aria-labelledby="webhooks" className="flex flex-col gap-3 rounded-lg border p-4">
      <h2 id="webhooks" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-xs">{t("intro")}</p>
      <ul className="flex flex-col gap-1 text-sm">
        {q.data.endpoints.map((e) => (
          <li key={e.id} className="flex flex-wrap gap-2">
            <code>{e.url}</code>
            <span className="text-muted-foreground">{e.events.join(", ")}</span>
            {!e.active ? <Badge variant="outline">{t("paused")}</Badge> : null}
          </li>
        ))}
      </ul>
      <form
        className="flex flex-col gap-2"
        onSubmit={(ev) => {
          ev.preventDefault();
          create.mutate();
        }}
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor={urlId}>{t("url")}</Label>
          <Input
            id={urlId}
            className="h-9"
            inputMode="url"
            placeholder="https://"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </div>
        <fieldset className="flex flex-wrap gap-3 text-sm">
          <legend className="mb-1">{t("events")}</legend>
          {q.data.events.map((name) => (
            <label key={name} className="flex items-center gap-1">
              <input
                type="checkbox"
                className="size-4"
                checked={events.includes(name)}
                onChange={(e) =>
                  setEvents((cur) =>
                    e.target.checked ? [...cur, name] : cur.filter((x) => x !== name),
                  )
                }
              />
              <code>{name}</code>
            </label>
          ))}
        </fieldset>
        <Button
          size="sm"
          className="self-start"
          disabled={!url || !events.length || create.isPending}
        >
          {t("add")}
        </Button>
        {create.error ? (
          <span role="alert" className="text-destructive text-sm">
            {errText(create.error, t("failed"))}
          </span>
        ) : null}
      </form>
      {secret ? (
        <p role="status" className="rounded-md border p-2 text-sm">
          {t("secretOnce")} <code className="break-all">{secret}</code>
        </p>
      ) : null}
      {q.data.deliveries.length ? (
        <table className="w-full text-sm">
          <caption className="sr-only">{t("log")}</caption>
          <thead>
            <tr className="text-muted-foreground text-left text-xs">
              <th scope="col">{t("event")}</th>
              <th scope="col">{t("status")}</th>
              <th scope="col">{t("attempts")}</th>
              <th scope="col">{t("when")}</th>
              <th scope="col">
                <span className="sr-only">{t("actions")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {q.data.deliveries.map((d) => (
              <tr key={d.id} className="border-t">
                <td className="py-1">
                  <code>{d.event_type}</code>
                </td>
                <td>
                  {t(`statuses.${d.status}`)}
                  {d.last_error ? ` (${d.last_error})` : ""}
                </td>
                <td className="tabular-nums">{d.attempts}</td>
                <td>
                  {format.dateTime(new Date(d.created_at), {
                    dateStyle: "short",
                    timeStyle: "short",
                  })}
                </td>
                <td>
                  <Button size="sm" variant="ghost" onClick={() => replay.mutate(d.id)}>
                    {t("replay")}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}

// --- API keys -----------------------------------------------------------------------------------
function ApiKeysSection() {
  const t = useTranslations("integrations.apiKeys");
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const q = useOrgQuery<ApiKey[]>("keys", "/hr/api-keys/");
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["jobs:read"]);
  const [token, setToken] = useState<string | null>(null);
  const nameId = useId();
  const refresh = () =>
    client.invalidateQueries({ queryKey: ["integrations", orgId ?? "", "keys"] });
  const create = useMutation({
    mutationFn: () =>
      api.post<{ key: string }>("/hr/api-keys/", { name, scopes }, { orgId: orgId! }),
    onSuccess: async (res) => {
      setToken(res.key);
      setName("");
      await refresh();
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/hr/api-keys/${id}/`, { orgId: orgId! }),
    onSuccess: refresh,
  });
  return (
    <section aria-labelledby="api-keys" className="flex flex-col gap-3 rounded-lg border p-4">
      <h2 id="api-keys" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-xs">{t("intro")}</p>
      <ul className="flex flex-col gap-1 text-sm">
        {(q.data ?? []).map((k) => (
          <li key={k.id} className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{k.name}</span>
            <code>mhrs_{k.prefix}_…</code>
            <span className="text-muted-foreground">{k.scopes.join(", ")}</span>
            {k.revoked_at ? (
              <Badge variant="outline">{t("revoked")}</Badge>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => revoke.mutate(k.id)}>
                {t("revoke")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor={nameId}>{t("name")}</Label>
          <Input
            id={nameId}
            className="h-9"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        {["jobs:read", "applications:read"].map((scope) => (
          <label key={scope} className="flex h-9 items-center gap-1 text-sm">
            <input
              type="checkbox"
              className="size-4"
              checked={scopes.includes(scope)}
              onChange={(e) =>
                setScopes((cur) =>
                  e.target.checked ? [...cur, scope] : cur.filter((s) => s !== scope),
                )
              }
            />
            <code>{scope}</code>
          </label>
        ))}
        <Button size="sm" disabled={!name || !scopes.length || create.isPending}>
          {t("create")}
        </Button>
      </form>
      {token ? (
        <p role="status" className="rounded-md border p-2 text-sm">
          {t("keyOnce")} <code className="break-all">{token}</code>
        </p>
      ) : null}
    </section>
  );
}

export function IntegrationsSettings() {
  const { role } = useJobsContext();
  const admin = role === "org_admin";
  return (
    <div className="flex flex-col gap-4">
      <Connections />
      {admin ? <WebhooksSection /> : null}
      {admin ? <ApiKeysSection /> : null}
    </div>
  );
}

// --- candidate: SMS / WhatsApp opt-in -----------------------------------------------------------
type Prefs = S["MessagingPreferences"];

export function MessagingPreferences() {
  const t = useTranslations("integrations.messaging");
  const client = useQueryClient();
  const q = useQuery({
    queryKey: ["messaging-preferences"],
    queryFn: () => api.get<Prefs>("/candidate/messaging-preferences/"),
  });
  const save = useMutation({
    mutationFn: (next: Prefs) => api.put<Prefs>("/candidate/messaging-preferences/", next),
    onSuccess: (data) => client.setQueryData(["messaging-preferences"], data),
  });
  if (!q.data) return null;
  const current = q.data;
  return (
    <fieldset className="flex flex-col gap-2 text-sm">
      <legend className="font-medium">{t("title")}</legend>
      <p className="text-muted-foreground text-xs">{t("intro")}</p>
      {(["sms", "whatsapp"] as const).map((channel) => (
        <label key={channel} className="flex items-center gap-2">
          <input
            type="checkbox"
            className="size-5"
            checked={current[channel]}
            disabled={save.isPending}
            onChange={(e) => save.mutate({ ...current, [channel]: e.target.checked })}
          />
          {t(channel)}
        </label>
      ))}
      {save.error ? (
        <p role="alert" className="text-destructive">
          {errText(save.error, t("failed"))}
        </p>
      ) : null}
    </fieldset>
  );
}

// --- staff SSO buttons --------------------------------------------------------------------------
interface AllauthConfig {
  data?: { socialaccount?: { providers?: { id: string; name: string }[] } };
}

/** Starts a Google/Microsoft sign-in through allauth (a form POST so the redirect is a page load). */
export function startSso(provider: string, next: string): void {
  const form = document.createElement("form");
  form.method = "POST";
  form.action = `${ALLAUTH_BASE}/auth/provider/redirect`;
  const fields: Record<string, string> = {
    provider,
    callback_url: next,
    process: "login",
    csrfmiddlewaretoken: getCookie("csrftoken") ?? "",
  };
  for (const [name, value] of Object.entries(fields)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
}

export function SsoButtons({ next = "/hr/dashboard" }: { next?: string }) {
  const t = useTranslations("auth.sso");
  const q = useQuery({
    queryKey: ["allauth-config"],
    queryFn: async () => {
      const res = await fetch(`${ALLAUTH_BASE}/config`, { credentials: "same-origin" });
      return (await res.json()) as AllauthConfig;
    },
    staleTime: 10 * 60_000,
    // set at build time for deployments where Google/Microsoft sign-in is configured
    enabled: process.env.NEXT_PUBLIC_SSO_ENABLED === "true",
  });
  const providers = q.data?.data?.socialaccount?.providers ?? [];
  if (!providers.length) return null;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted-foreground text-center text-xs">{t("or")}</p>
      {providers.map((p) => (
        <Button key={p.id} type="button" variant="outline" onClick={() => startSso(p.id, next)}>
          {t("with", { provider: p.name })}
        </Button>
      ))}
      <p className="text-muted-foreground text-xs">{t("staffOnly")}</p>
    </div>
  );
}
