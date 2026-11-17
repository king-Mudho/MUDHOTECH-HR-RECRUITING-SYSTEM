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
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

type Grant = components["schemas"]["Grant"];
type Active = components["schemas"]["ActiveSupport"];

/** Shown to every staff member of the organisation while platform support has read access. */
export function SupportBanner() {
  const t = useTranslations("support");
  const format = useFormatter();
  const { orgId } = useJobsContext();
  const active = useQuery({
    queryKey: ["support-active", orgId ?? ""],
    queryFn: () => api.get<Active>("/hr/support-access/active/", { orgId: orgId! }),
    enabled: !!orgId,
    refetchInterval: 60_000,
  });
  if (!active.data?.active) return null;
  return (
    <Alert role="status" className="mb-4">
      <AlertDescription>
        {t("banner", {
          until: active.data.until
            ? format.dateTime(new Date(active.data.until), { timeStyle: "short" })
            : "—",
          reason: active.data.reason,
        })}
      </AlertDescription>
    </Alert>
  );
}

function GrantRow({ grant, onRevoke }: { grant: Grant; onRevoke?: () => void }) {
  const t = useTranslations("support");
  const format = useFormatter();
  const when = (iso: string | null) =>
    iso ? format.dateTime(new Date(iso), { dateStyle: "medium", timeStyle: "short" }) : "—";
  return (
    <li className="rounded-md border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{grant.platform_user}</span>
        <span className="text-muted-foreground">{grant.organisation_name}</span>
        <Badge variant="outline">
          {grant.active
            ? t("status.active")
            : grant.revoked_at
              ? t("status.revoked")
              : grant.approved_at
                ? t("status.expired")
                : t("status.pending")}
        </Badge>
        {onRevoke && (grant.active || !grant.approved_at) && !grant.revoked_at ? (
          <Button size="sm" variant="outline" className="ml-auto" onClick={onRevoke}>
            {t("revoke")}
          </Button>
        ) : null}
      </div>
      <p className="mt-1">{grant.reason}</p>
      <p className="text-muted-foreground mt-1 text-xs">
        {t("meta", {
          requested: when(grant.requested_at),
          until: when(grant.expires_at),
          approver: grant.approved_by ?? "—",
          accesses: grant.accesses,
        })}
      </p>
    </li>
  );
}

/** Organisation admins: every support grant on their organisation, with revoke. */
export function OrgSupportAccess() {
  const t = useTranslations("support");
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const grants = useQuery({
    queryKey: ["support-grants", orgId ?? ""],
    queryFn: () => api.get<Grant[]>("/hr/support-access/", { orgId: orgId! }),
    enabled: !!orgId,
  });
  const revoke = useMutation({
    mutationFn: (id: string) =>
      api.post<Grant>(`/hr/support-access/${id}/revoke/`, undefined, { orgId: orgId! }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["support-grants", orgId ?? ""] }),
  });
  return (
    <section aria-labelledby="support-grants" className="flex flex-col gap-2">
      <h2 id="support-grants" className="text-lg font-semibold">
        {t("orgTitle")}
      </h2>
      <p className="text-muted-foreground text-sm">{t("orgIntro")}</p>
      {grants.isPending ? (
        <PageSkeleton rows={1} />
      ) : grants.isError ? (
        <ErrorState error={grants.error} onRetry={() => grants.refetch()} />
      ) : grants.data.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("none")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {grants.data.map((g) => (
            <GrantRow key={g.id} grant={g} onRevoke={() => revoke.mutate(g.id)} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** Platform: support requests access; a different platform admin approves. */
export function PlatformSupportAccess() {
  const t = useTranslations("support");
  const id = useId();
  const client = useQueryClient();
  const [form, setForm] = useState({ organisation_id: "", reason: "", minutes: "60" });
  const grants = useQuery({
    queryKey: ["platform-support-grants"],
    queryFn: () => api.get<Grant[]>("/platform/support-access/"),
  });
  const refresh = () => void client.invalidateQueries({ queryKey: ["platform-support-grants"] });
  const request = useMutation({
    mutationFn: () =>
      api.post<Grant>("/platform/support-access/", { ...form, minutes: Number(form.minutes) }),
    onSuccess: () => {
      setForm({ organisation_id: "", reason: "", minutes: "60" });
      refresh();
    },
  });
  const approve = useMutation({
    mutationFn: (grantId: string) =>
      api.post<Grant>(`/platform/support-access/${grantId}/approve/`),
    onSuccess: refresh,
  });
  const revoke = useMutation({
    mutationFn: (grantId: string) => api.post<Grant>(`/platform/support-access/${grantId}/revoke/`),
    onSuccess: refresh,
  });
  const error = [request.error, approve.error, revoke.error].find(Boolean);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">{t("platformTitle")}</h1>
      <p className="text-muted-foreground text-sm">{t("platformIntro")}</p>
      <form
        className="grid gap-2 sm:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          request.mutate();
        }}
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-org`}>{t("organisationId")}</Label>
          <Input
            id={`${id}-org`}
            value={form.organisation_id}
            onChange={(e) => setForm({ ...form, organisation_id: e.target.value.trim() })}
          />
        </div>
        <div className="flex flex-col gap-1 sm:col-span-2">
          <Label htmlFor={`${id}-reason`}>{t("reason")}</Label>
          <Input
            id={`${id}-reason`}
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-minutes`}>{t("minutes")}</Label>
          <Input
            id={`${id}-minutes`}
            type="number"
            min={5}
            max={240}
            value={form.minutes}
            onChange={(e) => setForm({ ...form, minutes: e.target.value })}
          />
        </div>
        <Button
          type="submit"
          size="sm"
          className="self-start"
          disabled={request.isPending || !form.organisation_id || form.reason.trim().length < 10}
        >
          {t("request")}
        </Button>
      </form>
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error instanceof ApiError ? error.message : t("failed")}
        </p>
      ) : null}
      {grants.isPending ? (
        <PageSkeleton rows={2} />
      ) : grants.isError ? (
        <ErrorState error={grants.error} onRetry={() => grants.refetch()} />
      ) : grants.data.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("none")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {grants.data.map((g) => (
            <div key={g.id} className="flex flex-col gap-1">
              <GrantRow grant={g} onRevoke={() => revoke.mutate(g.id)} />
              {!g.approved_at && !g.revoked_at ? (
                <Button size="sm" className="self-start" onClick={() => approve.mutate(g.id)}>
                  {t("approve")}
                </Button>
              ) : null}
            </div>
          ))}
        </ul>
      )}
    </div>
  );
}
