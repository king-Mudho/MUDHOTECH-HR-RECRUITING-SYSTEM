"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

export type Membership = components["schemas"]["TalentPoolMembership"];

export const talentPoolKey = ["privacy", "talent-pools"] as const;

/** What the candidate can do with one employer's pool in its current state. */
export function poolActions(m: Pick<Membership, "status" | "reconfirm_due">) {
  return {
    join: m.status !== "active",
    reconfirm: m.status === "active" && m.reconfirm_due,
    leave: m.status === "active",
    remove: m.status !== "none",
  };
}

export function TalentPools() {
  const t = useTranslations("privacy.talentPool");
  const format = useFormatter();
  const client = useQueryClient();
  const [deleting, setDeleting] = useState<Membership | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rows = useQuery({
    queryKey: talentPoolKey,
    queryFn: () => api.get<Membership[]>("/candidate/talent-pools/"),
  });
  const done = async () => {
    setError(null);
    setDeleting(null);
    await client.invalidateQueries({ queryKey: talentPoolKey });
    await client.invalidateQueries({ queryKey: ["privacy", "consents"] });
  };
  const fail = (err: unknown) => setError(err instanceof ApiError ? err.message : t("failed"));
  const join = useMutation({
    mutationFn: (orgId: string) =>
      api.post<Membership>("/candidate/talent-pools/", { organisation_id: orgId }),
    onSuccess: done,
    onError: fail,
  });
  const leave = useMutation({
    mutationFn: ({ orgId, remove }: { orgId: string; remove: boolean }) =>
      api.post<Membership>(`/candidate/talent-pools/${orgId}/leave/`, { delete: remove }),
    onSuccess: done,
    onError: fail,
  });
  const busy = join.isPending || leave.isPending;
  const date = (iso: string | null | undefined) =>
    iso ? format.dateTime(new Date(iso), { dateStyle: "medium" }) : "";
  return (
    <section id="talent-pool" aria-labelledby="talent-pool-title" className="rounded-lg border p-4">
      <h2 id="talent-pool-title" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-sm">{t("intro")}</p>
      {rows.isPending ? (
        <PageSkeleton rows={2} />
      ) : rows.isError ? (
        <ErrorState error={rows.error} onRetry={() => rows.refetch()} />
      ) : rows.data.length === 0 ? (
        <p className="text-muted-foreground mt-2 text-sm">{t("none")}</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2 text-sm">
          {rows.data.map((m) => {
            const can = poolActions(m);
            return (
              <li
                key={m.organisation_id}
                className="flex flex-wrap items-center gap-2 rounded-md border p-2"
              >
                <span className="font-medium">{m.organisation_name}</span>
                <Badge variant="outline">{t(`status.${m.status}`)}</Badge>
                {m.status === "active" ? (
                  <span className="text-muted-foreground">
                    {t("until", { date: date(m.expires_at) })}
                  </span>
                ) : null}
                {m.reconfirm_due ? (
                  <span className="text-sm font-medium">{t("endingSoon")}</span>
                ) : null}
                <span className="ml-auto flex flex-wrap gap-2">
                  {can.join ? (
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => join.mutate(m.organisation_id)}
                    >
                      {t("join")}
                    </Button>
                  ) : null}
                  {can.reconfirm ? (
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => join.mutate(m.organisation_id)}
                    >
                      {t("reconfirm")}
                    </Button>
                  ) : null}
                  {can.leave ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() => leave.mutate({ orgId: m.organisation_id, remove: false })}
                    >
                      {t("leave")}
                    </Button>
                  ) : null}
                  {can.remove ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => setDeleting(m)}
                    >
                      {t("delete")}
                    </Button>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <p aria-live="polite" className="text-destructive mt-2 text-sm">
        {deleting ? null : error}
      </p>
      {deleting ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setDeleting(null)}
          title={t("deleteTitle", { company: deleting.organisation_name })}
          description={t("deleteBody")}
          confirmLabel={t("delete")}
          destructive
          reason="none"
          pending={leave.isPending}
          error={error}
          onConfirm={() => leave.mutate({ orgId: deleting.organisation_id, remove: true })}
        />
      ) : null}
    </section>
  );
}
