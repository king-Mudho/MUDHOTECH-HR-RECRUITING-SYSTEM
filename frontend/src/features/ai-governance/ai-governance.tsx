"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";

import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMe } from "@/features/auth/session";
import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

type State = components["schemas"]["AIGovernance"];
type Entry = components["schemas"]["RegistryEntry"];

const KEY = ["platform-ai"];
const MIN_REASON = 10;

function ModelCard({ entry }: { entry: Entry }) {
  const t = useTranslations("aiGovernance");
  const format = useFormatter();
  const date = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium" });
  const kinds = ["rules", "embedding", "llm", "ner"] as const;
  const kind = kinds.find((k) => k === entry.kind);
  return (
    <li className="rounded-md border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">
          {entry.name}@{entry.version}
        </span>
        <span className="text-muted-foreground">{kind ? t(`kind.${kind}`) : entry.kind}</span>
        <Badge variant={entry.active ? "default" : "outline"} className="ml-auto">
          {entry.active ? t("active") : t("retired")}
        </Badge>
      </div>
      <dl className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-[max-content_1fr]">
        <dt className="text-muted-foreground">{t("fields.purpose")}</dt>
        <dd>{entry.purpose}</dd>
        <dt className="text-muted-foreground">{t("fields.provider")}</dt>
        <dd>{entry.provider}</dd>
        {entry.data_policy ? (
          <>
            <dt className="text-muted-foreground">{t("fields.dataPolicy")}</dt>
            <dd>{entry.data_policy}</dd>
          </>
        ) : null}
        {entry.limitations ? (
          <>
            <dt className="text-muted-foreground">{t("fields.limitations")}</dt>
            <dd>{entry.limitations}</dd>
          </>
        ) : null}
        {entry.evaluation_report ? (
          <>
            <dt className="text-muted-foreground">{t("fields.report")}</dt>
            <dd className="font-mono text-xs">{entry.evaluation_report}</dd>
          </>
        ) : null}
        <dt className="text-muted-foreground">{t("fields.period")}</dt>
        <dd>
          {entry.active_to
            ? t("between", { from: date(entry.active_from), to: date(entry.active_to) })
            : t("since", { from: date(entry.active_from) })}
        </dd>
      </dl>
    </li>
  );
}

/** Platform staff: model registry + AI kill-switch (P09-T11, docs/runbooks/disable-ai.md). */
export function AiGovernance() {
  const t = useTranslations("aiGovernance");
  const id = useId();
  const client = useQueryClient();
  const me = useMe();
  const canEdit = me.data?.platform_role === "platform_admin";
  const [reason, setReason] = useState("");
  const [orgId, setOrgId] = useState("");
  const state = useQuery({ queryKey: KEY, queryFn: () => api.get<State>("/platform/ai/") });
  const done = (data: State) => {
    client.setQueryData(KEY, data);
    setReason("");
    setOrgId("");
  };
  const platform = useMutation({
    mutationFn: (enabled: boolean) => api.post<State>("/platform/ai/", { enabled, reason }),
    onSuccess: done,
  });
  const org = useMutation({
    mutationFn: (v: { id: string; enabled: boolean | null }) =>
      api.post<State>(`/platform/ai/organisations/${v.id}/`, { enabled: v.enabled, reason }),
    onSuccess: done,
  });
  const reasonOk = reason.trim().length >= MIN_REASON;
  const error = platform.error ?? org.error;

  if (state.isPending) return <PageSkeleton rows={3} />;
  if (state.isError) return <ErrorState error={state.error} onRetry={() => state.refetch()} />;
  const data = state.data;
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t("intro")}</p>
      </header>

      <section aria-labelledby={`${id}-switch`} className="flex flex-col gap-3">
        <h2 id={`${id}-switch`} className="text-lg font-semibold">
          {t("switchTitle")}
        </h2>
        <Alert role="status" variant={data.platform_enabled ? "default" : "destructive"}>
          <AlertDescription>
            {data.platform_enabled ? t("platformOn") : t("platformOff")}
          </AlertDescription>
        </Alert>
        {canEdit ? (
          <div className="flex flex-col gap-1">
            <Label htmlFor={`${id}-reason`}>{t("reason")}</Label>
            <Input
              id={`${id}-reason`}
              value={reason}
              aria-describedby={`${id}-reason-hint`}
              onChange={(e) => setReason(e.target.value)}
            />
            <p id={`${id}-reason-hint`} className="text-muted-foreground text-xs">
              {t("reasonHint")}
            </p>
            <Button
              className="mt-1 self-start"
              variant={data.platform_enabled ? "destructive" : "default"}
              disabled={!reasonOk || platform.isPending}
              onClick={() => platform.mutate(!data.platform_enabled)}
            >
              {data.platform_enabled ? t("turnOff") : t("turnOn")}
            </Button>
          </div>
        ) : (
          <p className="text-muted-foreground text-sm">{t("readOnly")}</p>
        )}
        {error ? (
          <p role="alert" className="text-destructive text-sm">
            {error.message}
          </p>
        ) : null}
      </section>

      <section aria-labelledby={`${id}-orgs`} className="flex flex-col gap-2">
        <h2 id={`${id}-orgs`} className="text-lg font-semibold">
          {t("orgTitle")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("orgIntro")}</p>
        {data.disabled_organisations.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("noOverrides")}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {data.disabled_organisations.map((o) => (
              <li key={o.id} className="flex items-center gap-2 rounded-md border p-2 text-sm">
                <span className="font-medium">{o.name}</span>
                {canEdit ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="ml-auto"
                    disabled={!reasonOk || org.isPending}
                    onClick={() => org.mutate({ id: o.id, enabled: null })}
                  >
                    {t("orgClear")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {canEdit ? (
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor={`${id}-org`}>{t("organisationId")}</Label>
              <Input
                id={`${id}-org`}
                value={orgId}
                onChange={(e) => setOrgId(e.target.value.trim())}
              />
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={!reasonOk || !orgId || org.isPending}
              onClick={() => org.mutate({ id: orgId, enabled: false })}
            >
              {t("orgOff")}
            </Button>
          </div>
        ) : null}
      </section>

      <section aria-labelledby={`${id}-models`} className="flex flex-col gap-2">
        <h2 id={`${id}-models`} className="text-lg font-semibold">
          {t("modelsTitle")}
        </h2>
        <ul className="flex flex-col gap-2">
          {data.models.map((m) => (
            <ModelCard key={m.id} entry={m} />
          ))}
        </ul>
      </section>
    </div>
  );
}
