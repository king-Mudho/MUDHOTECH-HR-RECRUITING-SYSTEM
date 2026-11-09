"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Pencil } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMembers } from "@/features/organisations/hooks";
import { ApiError } from "@/lib/api-client";
import { formatInZone, utcIsoToZonedLocal, zonedLocalToUtcIso } from "@/lib/timezone";

import type { Assignment, JobAction, JobDetail, Readiness } from "../api";
import {
  canJob,
  jobKeys,
  useJob,
  useJobAssignments,
  useJobEvents,
  useJobVersions,
  useJobsContext,
} from "../hooks";
import { ReadinessPanel } from "./readiness-panel";

type ActionSpec = {
  action: JobAction;
  perm: "jobs.create" | "jobs.approve" | "jobs.publish";
  reason?: "none" | "optional" | "required";
  date?: "publish_at" | "closes_at";
  destructive?: boolean;
  primary?: boolean;
};

function actionsFor(job: JobDetail): ActionSpec[] {
  const v = job.version?.status;
  const list: ActionSpec[] = [];
  if (v === "in_review") {
    list.push({ action: "approve", perm: "jobs.approve", reason: "optional", primary: true });
    list.push({ action: "reject", perm: "jobs.approve", reason: "required" });
  }
  switch (job.status) {
    case "draft":
      if (v === "draft")
        list.push({ action: "submit-for-approval", perm: "jobs.create", primary: true });
      list.push({ action: "archive", perm: "jobs.publish", reason: "optional", destructive: true });
      break;
    case "approved":
      list.push({ action: "publish", perm: "jobs.publish", primary: true });
      list.push({ action: "schedule", perm: "jobs.publish", date: "publish_at" });
      list.push({ action: "new-version", perm: "jobs.approve", reason: "required" });
      list.push({ action: "archive", perm: "jobs.publish", reason: "optional", destructive: true });
      break;
    case "scheduled":
      list.push({ action: "publish", perm: "jobs.publish", primary: true });
      list.push({ action: "close", perm: "jobs.publish", reason: "required", destructive: true });
      break;
    case "published":
      if (v === "draft")
        list.push({ action: "submit-for-approval", perm: "jobs.create", primary: true });
      list.push({ action: "pause", perm: "jobs.publish", reason: "optional" });
      list.push({
        action: "extend-deadline",
        perm: "jobs.publish",
        reason: "required",
        date: "closes_at",
      });
      if (v === "approved")
        list.push({ action: "new-version", perm: "jobs.approve", reason: "required" });
      list.push({ action: "duplicate", perm: "jobs.create" });
      list.push({ action: "close", perm: "jobs.publish", reason: "required", destructive: true });
      break;
    case "paused":
      list.push({ action: "resume", perm: "jobs.publish", primary: true });
      list.push({
        action: "extend-deadline",
        perm: "jobs.publish",
        reason: "required",
        date: "closes_at",
      });
      list.push({ action: "close", perm: "jobs.publish", reason: "required", destructive: true });
      break;
    case "closed":
      list.push({
        action: "extend-deadline",
        perm: "jobs.publish",
        reason: "required",
        date: "closes_at",
      });
      list.push({ action: "duplicate", perm: "jobs.create" });
      list.push({ action: "archive", perm: "jobs.publish", reason: "optional" });
      break;
    case "archived":
      list.push({ action: "duplicate", perm: "jobs.create" });
      break;
  }
  return list;
}

function DateActionDialog({
  spec,
  job,
  open,
  onOpenChange,
  onConfirm,
  pending,
  error,
}: {
  spec: ActionSpec;
  job: JobDetail;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onConfirm: (body: Record<string, unknown>) => void;
  pending: boolean;
  error: string | null;
}) {
  const t = useTranslations("jobs.overview");
  const tf = useTranslations("forms");
  const id = useId();
  const [local, setLocal] = useState(() =>
    utcIsoToZonedLocal(spec.date === "closes_at" ? job.closes_at : null, job.timezone),
  );
  const [reason, setReason] = useState("");
  const iso = local ? zonedLocalToUtcIso(local, job.timezone) : null;
  const needsReason = spec.reason === "required";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(`actions.${spec.action}`)}</DialogTitle>
          <DialogDescription>{t(`confirm.${spec.action}`)}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${id}-date`}>
            {t(spec.date === "publish_at" ? "publishAt" : "newDeadline", { tz: job.timezone })}
          </Label>
          <Input
            id={`${id}-date`}
            type="datetime-local"
            className="h-10"
            value={local}
            onChange={(e) => setLocal(e.target.value)}
          />
        </div>
        {needsReason ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${id}-reason`}>
              {tf("reason")}{" "}
              <span className="text-muted-foreground font-normal">{tf("requiredMark")}</span>
            </Label>
            <textarea
              id={`${id}-reason`}
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="border-input bg-background rounded-md border px-3 py-2 text-sm"
            />
            <p className="text-muted-foreground text-xs">{tf("reasonHelp")}</p>
          </div>
        ) : null}
        {error ? (
          <p className="text-destructive text-sm" role="alert">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tf("cancel")}
          </Button>
          <Button
            disabled={pending || !iso || (needsReason && reason.trim().length < 5)}
            onClick={() =>
              onConfirm(
                spec.date === "publish_at" ? { publish_at: iso } : { closes_at: iso, reason },
              )
            }
          >
            {t(`actions.${spec.action}`)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ActionBar({ job }: { job: JobDetail }) {
  const t = useTranslations("jobs.overview");
  const { role, api, orgId } = useJobsContext();
  const client = useQueryClient();
  const router = useRouter();
  const [active, setActive] = useState<ActionSpec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notReady, setNotReady] = useState<Readiness | null>(null);
  const mutation = useMutation({
    mutationFn: ({ spec, body }: { spec: ActionSpec; body: Record<string, unknown> }) =>
      api!.action(job.id, spec.action, body),
    onSuccess: async (data, { spec }) => {
      setActive(null);
      setNotReady(null);
      await client.invalidateQueries({ queryKey: jobKeys.all(orgId!) });
      if (spec.action === "duplicate") router.push(`/hr/jobs/${data.id}/edit`);
      else if (spec.action === "new-version") router.push(`/hr/jobs/${job.id}/edit`);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "job_not_ready") {
        const checks = (err.details.checks ?? []) as Readiness["checks"];
        setNotReady({ ready: false, stage: "publish", checks, warnings: [] });
        setActive(null);
      }
      setError(err instanceof ApiError ? err.message : t("actionFailed"));
    },
  });
  const specs = actionsFor(job).filter((s) => canJob(role, s.perm));
  if (specs.length === 0) return null;
  const run = (spec: ActionSpec, body: Record<string, unknown> = {}) => {
    setError(null);
    mutation.mutate({ spec, body });
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label={t("actionsLabel")}>
        {specs.map((spec) => (
          <Button
            key={spec.action}
            variant={spec.primary ? "default" : spec.destructive ? "destructive" : "outline"}
            className="min-h-10"
            disabled={mutation.isPending}
            onClick={() => {
              setError(null);
              setActive(spec);
            }}
          >
            {t(`actions.${spec.action}`)}
          </Button>
        ))}
      </div>
      {error && !active ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {notReady ? <ReadinessPanel jobId={job.id} stage="publish" data={notReady} /> : null}
      {active?.date ? (
        <DateActionDialog
          key={active.action}
          spec={active}
          job={job}
          open
          onOpenChange={(o) => !o && setActive(null)}
          onConfirm={(body) => run(active, body)}
          pending={mutation.isPending}
          error={error}
        />
      ) : active ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setActive(null)}
          title={t(`actions.${active.action}`)}
          description={t(`confirm.${active.action}`)}
          confirmLabel={t(`actions.${active.action}`)}
          destructive={active.destructive}
          reason={active.reason ?? "none"}
          pending={mutation.isPending}
          error={error}
          onConfirm={(reason) =>
            run(
              active,
              active.action === "approve"
                ? { comment: reason }
                : active.reason && active.reason !== "none"
                  ? { reason }
                  : {},
            )
          }
        />
      ) : null}
    </div>
  );
}

function AssignmentsCard({ job }: { job: JobDetail }) {
  const t = useTranslations("jobs.assignments");
  const { role, orgId, api } = useJobsContext();
  const assignments = useJobAssignments(job.id);
  const canEdit = canJob(role, "jobs.assign");
  const members = useMembers(orgId ?? undefined, canEdit);
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [selection, setSelection] = useState<Record<string, Set<Assignment["role_on_job"]>>>({});
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () =>
      api!.setAssignments(
        job.id,
        Object.entries(selection).flatMap(([membership_id, roles]) =>
          [...roles].map((role_on_job) => ({ membership_id, role_on_job })),
        ),
      ),
    onSuccess: async () => {
      setEditing(false);
      await client.invalidateQueries({ queryKey: jobKeys.assignments(orgId!, job.id) });
      await client.invalidateQueries({
        queryKey: [...jobKeys.detail(orgId!, job.id), "readiness"],
      });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : t("failed")),
  });
  const startEdit = () => {
    const sel: Record<string, Set<Assignment["role_on_job"]>> = {};
    for (const a of assignments.data ?? []) (sel[a.membership] ??= new Set()).add(a.role_on_job);
    setSelection(sel);
    setError(null);
    setEditing(true);
  };
  const toggle = (id: string, r: Assignment["role_on_job"]) =>
    setSelection((prev) => {
      const next = { ...prev, [id]: new Set(prev[id] ?? []) };
      if (next[id]!.has(r)) next[id]!.delete(r);
      else next[id]!.add(r);
      return next;
    });
  const eligible: Record<Assignment["role_on_job"], string[]> = {
    recruiter: ["org_admin", "hr_manager", "recruiter"],
    hiring_manager: ["org_admin", "hr_manager", "recruiter", "hiring_manager"],
    approver: ["org_admin", "hr_manager"],
  };
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
        </CardTitle>
        {canEdit && !editing ? (
          <Button size="sm" variant="outline" onClick={startEdit}>
            {t("edit")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="text-sm">
        {assignments.isPending ? (
          <p className="text-muted-foreground">…</p>
        ) : editing ? (
          <div className="flex flex-col gap-3">
            <div className="overflow-x-auto">
              <table className="w-full">
                <caption className="sr-only">{t("title")}</caption>
                <thead>
                  <tr className="text-left">
                    <th scope="col" className="py-1 font-medium">
                      {t("member")}
                    </th>
                    {(["recruiter", "hiring_manager", "approver"] as const).map((r) => (
                      <th key={r} scope="col" className="py-1 font-medium">
                        {t(`roles.${r}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(members.data?.results ?? [])
                    .filter((m) => m.status === "active")
                    .map((m) => (
                      <tr key={m.id} className="border-t">
                        <th scope="row" className="py-1 text-left font-normal">
                          {m.user.display_name || m.user.email}
                        </th>
                        {(["recruiter", "hiring_manager", "approver"] as const).map((r) => (
                          <td key={r} className="py-1">
                            {eligible[r].includes(m.role) ? (
                              <input
                                type="checkbox"
                                className="size-4"
                                aria-label={`${m.user.display_name || m.user.email}: ${t(`roles.${r}`)}`}
                                checked={selection[m.id]?.has(r) ?? false}
                                onChange={() => toggle(m.id, r)}
                              />
                            ) : null}
                          </td>
                        ))}
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            {error ? (
              <p className="text-destructive" role="alert">
                {error}
              </p>
            ) : null}
            <div className="flex gap-2">
              <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
                {t("save")}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
                {t("cancel")}
              </Button>
            </div>
          </div>
        ) : (assignments.data ?? []).length === 0 ? (
          <p className="text-muted-foreground">{t("none")}</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {(assignments.data ?? []).map((a) => (
              <li key={a.id}>
                {a.user_name} — {t(`roles.${a.role_on_job}`)}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function HistoryCards({ job }: { job: JobDetail }) {
  const t = useTranslations("jobs.overview");
  const format = useFormatter();
  const versions = useJobVersions(job.id);
  const events = useJobEvents(job.id);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("versions")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          <ul className="flex flex-col gap-2">
            {(versions.data ?? []).map((v) => (
              <li key={v.id} className="flex flex-wrap items-center gap-2">
                <span className="font-medium">v{v.number}</span>
                <StatusBadge status={v.status} />
                {v.number === job.published_version_number ? (
                  <span className="text-success text-xs">{t("live")}</span>
                ) : null}
                {v.change_note ? (
                  <span className="text-muted-foreground">— {v.change_note}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("timeline")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          <ol className="flex flex-col gap-2">
            {(events.data ?? [])
              .slice()
              .reverse()
              .map((e) => (
                <li key={e.id}>
                  <span className="font-medium">
                    {t.has(`events.${e.action}`) ? t(`events.${e.action}`) : e.action}
                  </span>{" "}
                  <span className="text-muted-foreground">
                    ·{" "}
                    {format.dateTime(new Date(e.created_at), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                    {e.version_number ? ` · v${e.version_number}` : ""}
                  </span>
                  {e.reason ? <p className="text-muted-foreground">{e.reason}</p> : null}
                </li>
              ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}

export function JobOverview({ jobId }: { jobId: string }) {
  const t = useTranslations("jobs.overview");
  const { role, isPending, orgId } = useJobsContext();
  const job = useJob(jobId);
  if (isPending || job.isPending) return <PageSkeleton />;
  if (!orgId || !canJob(role, "jobs.view")) return <ForbiddenState />;
  if (job.isError) {
    if (job.error instanceof ApiError && job.error.status === 404)
      return <ForbiddenState title={t("notFoundTitle")} description={t("notFound")} />;
    return <ErrorState error={job.error} onRetry={() => job.refetch()} />;
  }
  const data = job.data;
  const v = data.version;
  const live = ["published", "paused", "closed"].includes(data.status);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Link
          href="/hr/jobs"
          className="text-muted-foreground text-sm underline-offset-2 hover:underline"
        >
          {t("backToJobs")}
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{data.title}</h1>
          <StatusBadge status={data.status} />
          {v ? (
            <span className="text-muted-foreground text-sm">
              {t("versionLabel", { n: v.number, status: v.status })}
            </span>
          ) : null}
        </div>
        <p className="text-muted-foreground text-sm">
          {data.closes_at
            ? t("closes", { when: formatInZone(data.closes_at, data.timezone) })
            : t("noDeadline")}
          {data.publish_at
            ? ` · ${t("scheduledFor", { when: formatInZone(data.publish_at, data.timezone) })}`
            : ""}
        </p>
        <div className="flex flex-wrap gap-2">
          {v?.status === "draft" && canJob(role, "jobs.create") ? (
            <Button asChild variant="outline" className="min-h-10">
              <Link href={`/hr/jobs/${data.id}/edit`}>
                <Pencil aria-hidden="true" />
                {data.published_version_number ? t("editNewVersion") : t("edit")}
              </Link>
            </Button>
          ) : null}
          {live ? (
            <Button asChild variant="outline" className="min-h-10">
              <Link href={`/jobs/${data.slug}`} target="_blank" rel="noopener">
                <ExternalLink aria-hidden="true" />
                {t("viewPublic")}
              </Link>
            </Button>
          ) : null}
        </div>
      </div>
      <ActionBar job={data} />
      {["in_review", "approved", "scheduled"].includes(data.status) || v?.status === "in_review" ? (
        <ReadinessPanel
          jobId={data.id}
          stage={data.status === "in_review" || v?.status === "in_review" ? "submit" : "publish"}
        />
      ) : null}
      <AssignmentsCard job={data} />
      <HistoryCards job={data} />
    </div>
  );
}
