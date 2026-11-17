"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

type Request = components["schemas"]["StaffRightsRequest"];
type Hold = components["schemas"]["LegalHold"];
type Action = "start" | "hold" | "complete" | "decline";

/** Mirrors backend `privacy.manage` (UI hiding only). */
const HANDLERS = ["org_admin"];
const NEXT: Record<string, Action[]> = {
  received: ["start", "hold", "complete", "decline"],
  in_progress: ["hold", "complete", "decline"],
  on_hold: ["start", "decline"],
};

function errorText(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : err ? fallback : null;
}

function Requests({ orgId }: { orgId: string }) {
  const t = useTranslations("privacy.staff");
  const tt = useTranslations("privacy.types");
  const ts = useTranslations("privacy.status");
  const format = useFormatter();
  const client = useQueryClient();
  const [pending, setPending] = useState<{ id: string; action: Action } | null>(null);
  const list = useQuery({
    queryKey: ["hr-privacy", orgId, "requests"],
    queryFn: () => api.get<Request[]>("/hr/privacy/requests/", { orgId }),
  });
  const act = useMutation({
    mutationFn: (vars: { id: string; action: Action; resolution: string }) =>
      api.post<Request>(
        `/hr/privacy/requests/${vars.id}/action/`,
        { action: vars.action, resolution: vars.resolution },
        { orgId },
      ),
    onSuccess: () => {
      setPending(null);
      void client.invalidateQueries({ queryKey: ["hr-privacy", orgId, "requests"] });
    },
  });
  return (
    <section aria-labelledby="privacy-requests" className="flex flex-col gap-2">
      <h2 id="privacy-requests" className="text-lg font-semibold">
        {t("requests")}
      </h2>
      {list.isPending ? (
        <PageSkeleton rows={2} />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.data.length === 0 ? (
        <EmptyState title={t("noneTitle")} description={t("none")} />
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {list.data.map((r) => (
            <li key={r.id} className="rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{tt(r.type)}</span>
                <Badge variant="outline">{ts(r.status)}</Badge>
                {r.overdue ? <Badge>{t("overdue")}</Badge> : null}
                <span className="text-muted-foreground font-mono text-xs">{r.reference}</span>
                <span className="text-muted-foreground ml-auto text-xs">
                  {t("due", { date: format.dateTime(new Date(r.due_at), { dateStyle: "medium" }) })}
                </span>
              </div>
              <p className="text-muted-foreground mt-1 text-xs">
                {t("from", { who: r.requester ?? "—" })}
              </p>
              {r.details ? <p className="mt-1 whitespace-pre-line">{r.details}</p> : null}
              {r.resolution ? (
                <p className="mt-1 text-xs">{t("resolution", { text: r.resolution })}</p>
              ) : null}
              {r.statement ? (
                <p className="mt-1 text-xs">{t("statement", { text: r.statement })}</p>
              ) : null}
              <div className="mt-2 flex flex-wrap gap-2">
                {(NEXT[r.status] ?? []).map((a) => (
                  <Button
                    key={a}
                    size="sm"
                    variant={a === "complete" ? "default" : "outline"}
                    onClick={() =>
                      a === "start"
                        ? act.mutate({ id: r.id, action: a, resolution: "" })
                        : setPending({ id: r.id, action: a })
                    }
                  >
                    {t(`actions.${a}`)}
                  </Button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => (o ? null : setPending(null))}
        title={pending ? t(`dialog.${pending.action}`) : ""}
        description={t("dialogHint")}
        confirmLabel={pending ? t(`actions.${pending.action}`) : ""}
        destructive={pending?.action === "decline"}
        reason="required"
        pending={act.isPending}
        error={errorText(act.error, t("failed"))}
        onConfirm={(resolution) =>
          pending && act.mutate({ id: pending.id, action: pending.action, resolution })
        }
      />
    </section>
  );
}

function Holds({ orgId }: { orgId: string }) {
  const t = useTranslations("privacy.holds");
  const format = useFormatter();
  const client = useQueryClient();
  const id = useId();
  const [target, setTarget] = useState({ target_type: "application", target_id: "", reason: "" });
  const holds = useQuery({
    queryKey: ["hr-privacy", orgId, "holds"],
    queryFn: () => api.get<Hold[]>("/hr/legal-holds/", { orgId }),
  });
  const refresh = () => void client.invalidateQueries({ queryKey: ["hr-privacy", orgId, "holds"] });
  const place = useMutation({
    mutationFn: () => api.post<Hold>("/hr/legal-holds/", target, { orgId }),
    onSuccess: () => {
      setTarget({ ...target, target_id: "", reason: "" });
      refresh();
    },
  });
  const release = useMutation({
    mutationFn: (holdId: string) =>
      api.post<Hold>(`/hr/legal-holds/${holdId}/release/`, undefined, { orgId }),
    onSuccess: refresh,
  });
  return (
    <section aria-labelledby="legal-holds" className="flex flex-col gap-2">
      <h2 id="legal-holds" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-sm">{t("intro")}</p>
      <form
        className="grid gap-2 sm:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          place.mutate();
        }}
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-type`}>{t("targetType")}</Label>
          <select
            id={`${id}-type`}
            className="border-input h-9 rounded-md border bg-transparent px-2 text-sm"
            value={target.target_type}
            onChange={(e) => setTarget({ ...target, target_type: e.target.value })}
          >
            {(["application", "candidate", "job"] as const).map((v) => (
              <option key={v} value={v}>
                {t(`targets.${v}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-id`}>{t("targetId")}</Label>
          <Input
            id={`${id}-id`}
            className="h-9"
            value={target.target_id}
            onChange={(e) => setTarget({ ...target, target_id: e.target.value.trim() })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-reason`}>{t("reason")}</Label>
          <Input
            id={`${id}-reason`}
            className="h-9"
            value={target.reason}
            onChange={(e) => setTarget({ ...target, reason: e.target.value })}
          />
        </div>
        <div className="flex items-end">
          <Button type="submit" size="sm" disabled={place.isPending || !target.target_id}>
            {t("place")}
          </Button>
        </div>
        {errorText(place.error, t("failed")) ? (
          <p role="alert" className="text-destructive text-sm sm:col-span-4">
            {errorText(place.error, t("failed"))}
          </p>
        ) : null}
      </form>
      {holds.isPending ? (
        <PageSkeleton rows={1} />
      ) : holds.isError ? (
        <ErrorState error={holds.error} onRetry={() => holds.refetch()} />
      ) : holds.data.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("none")}</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {holds.data.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center gap-2 rounded-md border p-2">
              <span>{t(`targets.${h.target_type}`)}</span>
              <span className="text-muted-foreground font-mono text-xs">{h.target_id}</span>
              <span className="text-muted-foreground text-xs">
                {format.dateTime(new Date(h.placed_at), { dateStyle: "medium" })}
              </span>
              {h.released_at ? (
                <Badge variant="outline" className="ml-auto">
                  {t("released")}
                </Badge>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto"
                  disabled={release.isPending}
                  onClick={() => release.mutate(h.id)}
                >
                  {t("release")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function HRPrivacy() {
  const t = useTranslations("privacy.staff");
  const { orgId, role, isPending } = useJobsContext();
  if (isPending) return <PageSkeleton />;
  if (!orgId || !HANDLERS.includes(role ?? ""))
    return <ForbiddenState description={t("forbidden")} />;
  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-xl font-semibold">{t("title")}</h2>
      <Requests orgId={orgId} />
      <Holds orgId={orgId} />
    </div>
  );
}
