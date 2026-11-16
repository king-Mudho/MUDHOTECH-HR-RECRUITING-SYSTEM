"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { useId, useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { APPLICATION_VIEWERS } from "@/features/hr-applications/api";
import { useJob, useJobsContext } from "@/features/jobs/hooks";
import { AiNotice, BandBadge } from "@/features/screening/components";
import { ApiError, api, newIdempotencyKey } from "@/lib/api-client";
import type { components } from "@/types/api";

type Shortlist = components["schemas"]["ShortlistDetail"];
type ShortlistRow = components["schemas"]["Shortlist"];
type Entry = Shortlist["entries"][number];
type Reason = components["schemas"]["DecisionReason"];

const EDITORS = ["org_admin", "hr_manager", "recruiter"];
const APPROVERS = ["org_admin", "hr_manager"];
const DECISIONS = ["shortlist", "hold", "not_selected", "undecided"] as const;
const UNCERTAIN = ["review_needed", "eligibility_review", "manual_review_requested"];
const LOW = 0.6;

export function isOverride(decision: string, band: string) {
  if (decision === "shortlist") return band === "lower_match" || band === "eligibility_review";
  if (decision === "not_selected") return band === "recommended_for_review";
  return false;
}

/** The four review columns (docs/08 §3.4 plus a separate low-coverage column). */
export function columnOf(e: Entry): "suggested" | "review" | "low" | "others" {
  if (e.ai_band === "recommended_for_review" && (e.coverage ?? 1) >= LOW) return "suggested";
  if (e.coverage !== null && e.coverage < LOW) return "low";
  if (UNCERTAIN.includes(e.ai_band)) return "review";
  return "others";
}

function useShortlists(jobId: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: ["shortlists", orgId ?? "", "job", jobId],
    queryFn: () => api.get<ShortlistRow[]>(`/hr/jobs/${jobId}/shortlists/`, { orgId: orgId! }),
    enabled: !!orgId,
  });
}

function useShortlist(id: string | undefined) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: ["shortlists", orgId ?? "", id],
    queryFn: () => api.get<Shortlist>(`/hr/shortlists/${id}/`, { orgId: orgId! }),
    enabled: !!orgId && !!id,
    refetchInterval: (q) => (q.state.data?.status === "approved" ? 15000 : false),
  });
}

function useReasons() {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: ["hr-decision-reasons", orgId ?? "", "all"],
    queryFn: () => api.get<Reason[]>("/hr/decision-reasons/", { orgId: orgId! }),
    enabled: !!orgId,
    staleTime: 5 * 60_000,
  });
}

function errorText(err: unknown, fallback: string) {
  return err instanceof ApiError ? err.message : err ? fallback : null;
}

function EntryCard({
  entry,
  editable,
  reasons,
  onDecide,
  pending,
}: {
  entry: Entry;
  editable: boolean;
  reasons: Reason[];
  onDecide: (decision: string, reasonCode: string, reasonText: string) => void;
  pending: boolean;
}) {
  const t = useTranslations("shortlisting");
  const id = useId();
  const [draft, setDraft] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [text, setText] = useState("");
  const decision = draft ?? entry.decision;
  const override = isOverride(decision, entry.ai_band);
  const needsReason = decision === "not_selected" || decision === "hold" || override;
  const lists = [
    decision === "shortlist" ? "shortlist" : decision,
    ...(override ? ["override"] : []),
  ];
  const options = reasons.filter((r) => lists.includes(r.applies_to));
  const choose = (d: string) => {
    if (d === "undecided" || (d === "shortlist" && !isOverride(d, entry.ai_band))) {
      setDraft(null);
      onDecide(d, "", "");
    } else {
      setDraft(d);
      setCode("");
    }
  };
  return (
    <li className="rounded-md border p-3 text-sm" aria-label={entry.candidate_name}>
      <div className="flex flex-wrap items-center gap-2">
        <Link href={`/hr/applications/${entry.application_id}`} className="font-medium underline">
          {entry.candidate_name || entry.reference}
        </Link>
        {entry.ai_band ? <BandBadge band={entry.ai_band} /> : null}
        <span className="text-muted-foreground ml-auto text-xs">
          {entry.score === null ? "—" : Math.round(entry.score)}
          {entry.coverage !== null
            ? ` · ${t("coverage", { value: Math.round(entry.coverage * 100) })}`
            : ""}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        {entry.suggestion === "shortlist" ? (
          <Badge variant="outline">{t("suggested")}</Badge>
        ) : null}
        {entry.override ? <Badge variant="outline">{t("overrideBadge")}</Badge> : null}
        {entry.apply_note ? (
          <Badge variant="outline">{t(`applyNote.${entry.apply_note.split(":")[0]}`)}</Badge>
        ) : null}
      </div>
      <div
        role="group"
        aria-label={t("decisionFor", { name: entry.candidate_name })}
        className="mt-2 flex flex-wrap gap-1"
      >
        {DECISIONS.map((d) => (
          <Button
            key={d}
            size="sm"
            variant={decision === d ? "default" : "outline"}
            aria-pressed={decision === d}
            disabled={!editable || pending}
            onClick={() => choose(d)}
          >
            {t(`decisions.${d}`)}
          </Button>
        ))}
      </div>
      {editable && draft && needsReason ? (
        <form
          className="mt-2 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            onDecide(draft, code, text);
            setDraft(null);
          }}
        >
          {override ? <p className="text-xs">{t("overrideHint")}</p> : null}
          <Label htmlFor={`${id}-reason`}>{t("reason")}</Label>
          <select
            id={`${id}-reason`}
            className="border-input h-9 rounded-md border bg-transparent px-2"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          >
            <option value="">{t("chooseReason")}</option>
            {options.map((r) => (
              <option key={`${r.applies_to}-${r.code}`} value={r.code}>
                {r.label}
              </option>
            ))}
          </select>
          {code === "other" ? (
            <>
              <Label htmlFor={`${id}-text`}>{t("explain")}</Label>
              <Input id={`${id}-text`} value={text} onChange={(e) => setText(e.target.value)} />
            </>
          ) : null}
          <div className="flex gap-2">
            <Button
              type="submit"
              size="sm"
              disabled={!code || (code === "other" && text.trim().length < 5) || pending}
            >
              {t("save")}
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => setDraft(null)}>
              {t("cancel")}
            </Button>
          </div>
        </form>
      ) : entry.reason_code ? (
        <p className="text-muted-foreground mt-1 text-xs">
          {reasons.find((r) => r.code === entry.reason_code)?.label ?? entry.reason_code}
        </p>
      ) : null}
    </li>
  );
}

function Summary({ s }: { s: Shortlist }) {
  const t = useTranslations("shortlisting");
  const c = s.summary;
  return (
    <p role="status" aria-live="polite" className="bg-muted/40 rounded-md border p-2 text-sm">
      {t("summary", {
        shortlist: c.shortlist,
        hold: c.hold,
        notSelected: c.not_selected,
        undecided: c.undecided,
      })}
      {c.overrides ? ` · ${t("overrides", { count: c.overrides })}` : ""}
      {c.above_desired_size ? ` · ${t("aboveSize", { size: s.desired_size ?? 0 })}` : ""}
    </p>
  );
}

function UndoCountdown({ s, onUndo }: { s: Shortlist; onUndo: () => void }) {
  const t = useTranslations("shortlisting");
  const now = useNow({ updateInterval: 1000 });
  const format = useFormatter();
  if (!s.notify_after) return null;
  const left = Math.max(0, new Date(s.notify_after).getTime() - now.getTime());
  if (left === 0)
    return (
      <Alert>
        <AlertDescription>{t("notified")}</AlertDescription>
      </Alert>
    );
  const minutes = Math.floor(left / 60000);
  const seconds = Math.floor((left % 60000) / 1000);
  return (
    <Alert>
      <AlertTitle>{t("approvedTitle")}</AlertTitle>
      <AlertDescription className="flex flex-wrap items-center gap-2">
        <span>
          {t("undoWindow", {
            time: `${minutes}:${String(seconds).padStart(2, "0")}`,
            at: format.dateTime(new Date(s.notify_after), { timeStyle: "short" }),
          })}
        </span>
        <Button size="sm" variant="outline" onClick={onUndo}>
          {t("undo")}
        </Button>
      </AlertDescription>
    </Alert>
  );
}

export function ShortlistBuilder({ jobId }: { jobId: string }) {
  const t = useTranslations("shortlisting");
  const { orgId, role, isPending } = useJobsContext();
  const client = useQueryClient();
  const job = useJob(jobId);
  const list = useShortlists(jobId);
  const latest = list.data?.[0];
  const detail = useShortlist(latest?.id);
  const reasons = useReasons();
  const [size, setSize] = useState("10");
  const [dialog, setDialog] = useState<"" | "approve" | "return" | "undo">("");
  const [leaveUndecided, setLeaveUndecided] = useState(false);
  const sizeId = useId();
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["shortlists", orgId ?? ""] });
    void client.invalidateQueries({ queryKey: ["hr-applications", orgId ?? ""] });
  };
  const base = latest ? `/hr/shortlists/${latest.id}` : "";
  const o = { orgId: orgId! };
  const propose = useMutation({
    mutationFn: () =>
      api.post<Shortlist>(
        `/hr/jobs/${jobId}/shortlists/`,
        { desired_size: Number(size) || null },
        o,
      ),
    onSuccess: refresh,
  });
  const decide = useMutation({
    mutationFn: (item: Record<string, string>) =>
      api.patch<Shortlist>(
        `${base}/entries/`,
        { decisions: [item], lock_version: detail.data?.lock_version },
        o,
      ),
    onSuccess: (data) => client.setQueryData(["shortlists", orgId ?? "", latest?.id], data),
    onError: refresh,
  });
  const action = useMutation({
    mutationFn: ({
      path,
      body,
      key,
    }: {
      path: string;
      body: Record<string, unknown>;
      key?: string;
    }) => api.post<Shortlist>(`${base}/${path}/`, body, { ...o, idempotencyKey: key }),
    onSuccess: () => {
      setDialog("");
      refresh();
    },
  });

  if (isPending) return <PageSkeleton />;
  if (!orgId || !role || !APPLICATION_VIEWERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  const s = detail.data;
  const canEdit = EDITORS.includes(role) && s?.status === "draft";
  const canApprove = APPROVERS.includes(role) && s?.status === "pending_approval";
  const open = !!s && ["draft", "pending_approval"].includes(s.status);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link href={`/hr/jobs/${jobId}/applications`} className="text-sm underline">
          {t("back")}
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">
          {t("title", { job: job.data?.title ?? "" })}
        </h1>
        <AiNotice />
      </div>

      {list.isPending || (latest && detail.isPending) ? (
        <PageSkeleton />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : !open && EDITORS.includes(role) && s?.status !== "approved" ? (
        <form
          className="flex flex-wrap items-end gap-2 rounded-lg border p-4"
          onSubmit={(e) => {
            e.preventDefault();
            propose.mutate();
          }}
        >
          <div className="flex flex-col gap-1">
            <Label htmlFor={sizeId}>{t("desiredSize")}</Label>
            <Input
              id={sizeId}
              type="number"
              min={1}
              max={1000}
              value={size}
              onChange={(e) => setSize(e.target.value)}
              className="h-9 w-28"
            />
          </div>
          <Button type="submit" disabled={propose.isPending}>
            {t("propose")}
          </Button>
          <p className="text-muted-foreground w-full text-xs">{t("proposeHint")}</p>
          {errorText(propose.error, t("failed")) ? (
            <p role="alert" className="text-destructive w-full text-sm">
              {errorText(propose.error, t("failed"))}
            </p>
          ) : null}
        </form>
      ) : null}

      {!s ? (
        !EDITORS.includes(role) ? (
          <EmptyState title={t("noneTitle")} description={t("none")} />
        ) : null
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{t(`status.${s.status}`)}</Badge>
            {s.desired_size ? (
              <span className="text-muted-foreground text-sm">
                {t("desired", { size: s.desired_size })}
              </span>
            ) : null}
          </div>
          {s.status === "draft" && s.return_reason ? (
            <Alert>
              <AlertTitle>{t("returnedTitle")}</AlertTitle>
              <AlertDescription>{s.return_reason}</AlertDescription>
            </Alert>
          ) : null}
          {s.status === "approved" && APPROVERS.includes(role) ? (
            <UndoCountdown s={s} onUndo={() => setDialog("undo")} />
          ) : null}
          <Summary s={s} />
          {errorText(decide.error, t("failed")) ? (
            <p role="alert" className="text-destructive text-sm">
              {errorText(decide.error, t("failed"))}
            </p>
          ) : null}
          <div className="grid gap-4 lg:grid-cols-4">
            {(["suggested", "review", "low", "others"] as const).map((col) => {
              const entries = s.entries.filter((e) => columnOf(e) === col);
              return (
                <section key={col} aria-labelledby={`col-${col}`} className="flex flex-col gap-2">
                  <h2 id={`col-${col}`} className="text-sm font-semibold">
                    {t(`columns.${col}`)} ({entries.length})
                  </h2>
                  {entries.length === 0 ? (
                    <p className="text-muted-foreground text-xs">{t("emptyColumn")}</p>
                  ) : (
                    <ul className="flex flex-col gap-2">
                      {entries.map((e) => (
                        <EntryCard
                          key={e.id}
                          entry={e}
                          editable={canEdit}
                          reasons={reasons.data ?? []}
                          pending={decide.isPending}
                          onDecide={(decision, code, text) =>
                            decide.mutate({
                              application_id: e.application_id,
                              decision,
                              reason_code: code,
                              reason_text: text,
                            })
                          }
                        />
                      ))}
                    </ul>
                  )}
                </section>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-2">
            {canEdit ? (
              <Button
                disabled={action.isPending || s.summary.total === s.summary.undecided}
                onClick={() =>
                  action.mutate({ path: "submit", body: { lock_version: s.lock_version } })
                }
              >
                {t("submit")}
              </Button>
            ) : null}
            {canApprove ? (
              <>
                <Button onClick={() => setDialog("approve")}>{t("approve")}</Button>
                <Button variant="outline" onClick={() => setDialog("return")}>
                  {t("return")}
                </Button>
              </>
            ) : null}
            {s.status === "pending_approval" && !APPROVERS.includes(role) ? (
              <p className="text-muted-foreground text-sm">{t("waiting")}</p>
            ) : null}
          </div>
          {errorText(action.error, t("failed")) && !dialog ? (
            <p role="alert" className="text-destructive text-sm">
              {errorText(action.error, t("failed"))}
            </p>
          ) : null}
          <ApprovalDialogs
            s={s}
            dialog={dialog}
            setDialog={setDialog}
            leaveUndecided={leaveUndecided}
            setLeaveUndecided={setLeaveUndecided}
            pending={action.isPending}
            error={errorText(action.error, t("failed"))}
            onApprove={() =>
              action.mutate({
                path: "approve",
                body: { lock_version: s.lock_version, leave_undecided: leaveUndecided },
                key: newIdempotencyKey(),
              })
            }
            onReturn={(reason) => action.mutate({ path: "reject", body: { reason } })}
            onUndo={(reason) => action.mutate({ path: "undo", body: { reason } })}
          />
        </>
      )}
    </div>
  );
}

function ApprovalDialogs({
  s,
  dialog,
  setDialog,
  leaveUndecided,
  setLeaveUndecided,
  pending,
  error,
  onApprove,
  onReturn,
  onUndo,
}: {
  s: Shortlist;
  dialog: "" | "approve" | "return" | "undo";
  setDialog: (d: "" | "approve" | "return" | "undo") => void;
  leaveUndecided: boolean;
  setLeaveUndecided: (v: boolean) => void;
  pending: boolean;
  error: string | null;
  onApprove: () => void;
  onReturn: (reason: string) => void;
  onUndo: (reason: string) => void;
}) {
  const t = useTranslations("shortlisting");
  const c = s.summary;
  const reasonLines = useMemo(() => Object.entries(c.reasons), [c.reasons]);
  const blocked = c.undecided > 0 && !leaveUndecided;
  return (
    <>
      <ConfirmDialog
        open={dialog === "approve"}
        onOpenChange={(o) => setDialog(o ? "approve" : "")}
        title={t("approveTitle")}
        confirmLabel={t("approveConfirm")}
        pending={pending || blocked}
        error={error}
        onConfirm={onApprove}
        description={
          <span className="flex flex-col gap-2">
            <span>
              {t("summary", {
                shortlist: c.shortlist,
                hold: c.hold,
                notSelected: c.not_selected,
                undecided: c.undecided,
              })}
            </span>
            {c.uncertain_not_selected ? (
              <span>{t("uncertainWarning", { count: c.uncertain_not_selected })}</span>
            ) : null}
            {reasonLines.length ? (
              <span>
                {t("reasonsUsed")}: {reasonLines.map(([k, v]) => `${k} (${v})`).join(", ")}
              </span>
            ) : null}
            <span>{t("approveNote")}</span>
            {c.undecided ? (
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  className="size-4"
                  checked={leaveUndecided}
                  onChange={(e) => setLeaveUndecided(e.target.checked)}
                />
                {t("leaveUndecided", { count: c.undecided })}
              </label>
            ) : null}
          </span>
        }
      />
      <ConfirmDialog
        open={dialog === "return"}
        onOpenChange={(o) => setDialog(o ? "return" : "")}
        title={t("returnTitle")}
        confirmLabel={t("return")}
        reason="required"
        pending={pending}
        error={error}
        onConfirm={onReturn}
      />
      <ConfirmDialog
        open={dialog === "undo"}
        onOpenChange={(o) => setDialog(o ? "undo" : "")}
        title={t("undoTitle")}
        description={t("undoDescription")}
        confirmLabel={t("undo")}
        destructive
        reason="required"
        pending={pending}
        error={error}
        onConfirm={onUndo}
      />
    </>
  );
}

export function ShortlistRoute() {
  const { id } = useParams<{ id: string }>();
  return <ShortlistBuilder jobId={id} />;
}
