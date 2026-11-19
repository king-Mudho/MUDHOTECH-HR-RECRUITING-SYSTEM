"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useMemo, useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { applyServerErrors } from "@/features/auth/form-errors";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError } from "@/lib/api-client";

import {
  FEEDBACK,
  MANAGERS,
  addDays,
  fromLocalInput,
  groupByDay,
  useApplicationInterviews,
  useFeedback,
  useInterview,
  useInterviewList,
  useInterviewMutation,
  usePanelOptions,
  useScorecards,
  useTemplates,
  weekStart,
  type Interview,
  type PanelView,
  type Scheduled,
  type Scorecard,
  type ScorecardInput,
  type ScorecardTemplate,
} from "./api";

const MODES = ["video", "in_person", "phone"] as const;
const RECOMMENDATIONS = ["strong_yes", "yes", "no", "strong_no"] as const;

function errorText(err: unknown, fallback: string): string | null {
  return err instanceof ApiError ? err.message : err ? fallback : null;
}

// ------------------------------------------------------------------------------ list / calendar
export function InterviewsRoute() {
  const t = useTranslations("interviews");
  const format = useFormatter();
  const { role, isPending: roleLoading } = useJobsContext();
  const [view, setView] = useState<"day" | "week">("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const [mine, setMine] = useState(false);
  const mineId = useId();
  const start = view === "week" ? weekStart(anchor) : new Date(anchor.toDateString());
  const end = addDays(start, view === "week" ? 7 : 1);
  const list = useInterviewList({ from: start.toISOString(), to: end.toISOString(), mine });
  const groups = useMemo(() => groupByDay(list.data?.results ?? []), [list.data]);

  if (roleLoading) return <PageSkeleton />;
  if (!role) return <ForbiddenState description={t("forbidden")} />;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label={t("viewLabel")} className="flex gap-1">
          {(["day", "week"] as const).map((v) => (
            <Button
              key={v}
              size="sm"
              variant={view === v ? "default" : "outline"}
              aria-pressed={view === v}
              onClick={() => setView(v)}
            >
              {t(`view.${v}`)}
            </Button>
          ))}
        </div>
        <Button
          size="sm"
          variant="outline"
          aria-label={t("previous")}
          onClick={() => setAnchor(addDays(anchor, view === "week" ? -7 : -1))}
        >
          ‹
        </Button>
        <Button size="sm" variant="outline" onClick={() => setAnchor(new Date())}>
          {t("today")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-label={t("next")}
          onClick={() => setAnchor(addDays(anchor, view === "week" ? 7 : 1))}
        >
          ›
        </Button>
        <span aria-live="polite" className="text-sm font-medium">
          {format.dateTimeRange(start, addDays(end, -1), { dateStyle: "medium" })}
        </span>
        <label htmlFor={mineId} className="ml-auto flex items-center gap-2 text-sm">
          <input
            id={mineId}
            type="checkbox"
            checked={mine}
            onChange={(e) => setMine(e.target.checked)}
          />
          {t("onlyMine")}
        </label>
      </div>
      {list.isPending ? (
        <PageSkeleton />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState title={t("emptyTitle")} description={t("empty")} />
      ) : (
        groups.map((g) => (
          <section key={g.day ?? "unscheduled"} aria-label={g.day ?? t("unscheduled")}>
            <h2 className="text-muted-foreground mb-2 text-sm font-semibold">
              {g.day
                ? format.dateTime(new Date(`${g.day}T12:00:00`), { dateStyle: "full" })
                : t("unscheduled")}
            </h2>
            <ul className="flex flex-col gap-2">
              {g.items.map((iv) => (
                <li key={iv.id}>
                  <InterviewRow iv={iv} />
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}

function InterviewRow({ iv }: { iv: Interview }) {
  const t = useTranslations("interviews");
  const format = useFormatter();
  return (
    <Link
      href={`/hr/interviews/${iv.id}`}
      className="hover:bg-muted flex flex-wrap items-center gap-3 rounded-lg border p-3"
    >
      <span className="min-w-28 text-sm font-semibold">
        {iv.starts_at
          ? format.dateTime(new Date(iv.starts_at), { timeStyle: "short" })
          : t("awaitingBooking")}
      </span>
      <span className="flex-1">
        <span className="font-medium">{iv.stage}</span>
        <span className="text-muted-foreground text-sm">
          {" · "}
          {iv.job_title} · {iv.reference}
        </span>
      </span>
      <Badge variant="outline">{t(`mode.${iv.mode}`)}</Badge>
      <Badge variant={iv.status === "scheduled" ? "default" : "secondary"}>
        {t(`status.${iv.status}`)}
      </Badge>
    </Link>
  );
}

// ------------------------------------------------------------------------------ detail
export function InterviewDetailRoute() {
  const { id } = useParams<{ id: string }>();
  return <InterviewDetail id={id} />;
}

function InterviewDetail({ id }: { id: string }) {
  const t = useTranslations("interviews");
  const format = useFormatter();
  const { role } = useJobsContext();
  const detail = useInterview(id);
  if (detail.isPending) return <PageSkeleton />;
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  const v = detail.data;
  const iv = v.interview;
  const when = iv.starts_at
    ? `${format.dateTime(new Date(iv.starts_at), { dateStyle: "full", timeStyle: "short" })}`
    : t("awaitingBooking");
  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link href="/hr/interviews" className="text-sm underline">
          {t("back")}
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">
          {iv.stage} · {iv.job_title}
        </h1>
        <p className="text-muted-foreground text-sm">
          <Link href={`/hr/applications/${iv.application_id}`} className="underline">
            {iv.reference}
          </Link>
        </p>
      </div>
      <section
        aria-labelledby="iv-when"
        className="grid gap-2 rounded-lg border p-4 sm:grid-cols-2"
      >
        <h2 id="iv-when" className="sr-only">
          {t("details")}
        </h2>
        <p>
          <span className="font-medium">{t("when")}: </span>
          {when} <span className="text-muted-foreground text-xs">({iv.timezone})</span>
        </p>
        <p>
          <span className="font-medium">{t("statusLabel")}: </span>
          {t(`status.${iv.status}`)}
        </p>
        <p>
          <span className="font-medium">{t("modeLabel")}: </span>
          {t(`mode.${iv.mode}`)}
          {iv.location ? ` · ${iv.location}` : ""}
        </p>
        {iv.video_link ? (
          <p>
            <a href={iv.video_link} className="underline" rel="noopener noreferrer" target="_blank">
              {t("joinLink")}
            </a>
          </p>
        ) : null}
        {iv.status_reason ? (
          <p className="sm:col-span-2">
            <span className="font-medium">{t("note")}: </span>
            {iv.status_reason}
          </p>
        ) : null}
        <p className="sm:col-span-2">
          <span className="font-medium">{t("panel")}: </span>
          {iv.panel
            .map(
              (p) =>
                `${p.name}${p.role === "lead" ? ` (${t("lead")})` : ""}${p.submitted ? " ✓" : ""}`,
            )
            .join(", ")}
        </p>
      </section>
      {v.can_manage ? <ManageActions iv={iv} /> : null}
      {v.ai ? (
        <Alert>
          <AlertTitle>{v.ai.notice}</AlertTitle>
          <AlertDescription>{t("aiBand", { band: v.ai.band || "-" })}</AlertDescription>
        </Alert>
      ) : null}
      <section aria-labelledby="iv-docs" className="rounded-lg border p-4">
        <h2 id="iv-docs" className="text-lg font-semibold">
          {t("documents")}
        </h2>
        {v.documents.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("noDocuments")}</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-1">
            {v.documents.map((d) => (
              <li key={d.id}>
                {d.available ? (
                  <a className="underline" href={`/api/v1/documents/${d.id}/download/`}>
                    {d.filename}
                  </a>
                ) : (
                  <span className="text-muted-foreground">{d.filename}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      <ScorecardSection view={v} />
      {role && FEEDBACK.includes(role) ? <FeedbackSection id={iv.id} /> : null}
    </div>
  );
}

// ------------------------------------------------------------------------------ manage actions
function ManageActions({ iv }: { iv: Interview }) {
  const t = useTranslations("interviews.manage");
  const [dialog, setDialog] = useState<"" | "cancel" | "noShow" | "reschedule">("");
  const cancel = useInterviewMutation<{ reason: string }, Interview>(
    () => `/hr/interviews/${iv.id}/cancel/`,
  );
  const noShow = useInterviewMutation<{ note: string }, Interview>(
    () => `/hr/interviews/${iv.id}/no-show/`,
  );
  const complete = useInterviewMutation<Record<string, never>, Interview>(
    () => `/hr/interviews/${iv.id}/complete/`,
  );
  const started = iv.starts_at ? new Date(iv.starts_at) <= new Date() : false;
  const open = iv.status === "proposed" || iv.status === "scheduled";
  const error = errorText(cancel.error ?? noShow.error ?? complete.error, t("failed"));
  if (!open) return null;
  return (
    <section aria-label={t("title")} className="flex flex-wrap gap-2">
      <Button size="sm" variant="outline" onClick={() => setDialog("reschedule")}>
        {t("reschedule")}
      </Button>
      <Button size="sm" variant="outline" onClick={() => setDialog("cancel")}>
        {t("cancel")}
      </Button>
      {iv.status === "scheduled" && started ? (
        <>
          <Button size="sm" onClick={() => complete.mutate({})} disabled={complete.isPending}>
            {t("complete")}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setDialog("noShow")}>
            {t("noShow")}
          </Button>
        </>
      ) : null}
      {error ? (
        <p role="alert" className="text-destructive w-full text-sm">
          {error}
        </p>
      ) : null}
      <ConfirmDialog
        open={dialog === "cancel"}
        onOpenChange={(o) => setDialog(o ? "cancel" : "")}
        title={t("cancelTitle")}
        description={t("cancelHelp")}
        confirmLabel={t("cancel")}
        destructive
        reason="required"
        pending={cancel.isPending}
        onConfirm={(reason) => cancel.mutate({ reason }, { onSuccess: () => setDialog("") })}
      />
      <ConfirmDialog
        open={dialog === "noShow"}
        onOpenChange={(o) => setDialog(o ? "noShow" : "")}
        title={t("noShowTitle")}
        description={t("noShowHelp")}
        confirmLabel={t("noShow")}
        reason="optional"
        pending={noShow.isPending}
        onConfirm={(note) => noShow.mutate({ note }, { onSuccess: () => setDialog("") })}
      />
      <RescheduleDialog
        iv={iv}
        open={dialog === "reschedule"}
        onOpenChange={(o) => setDialog(o ? "reschedule" : "")}
      />
    </section>
  );
}

const rescheduleSchema = z.object({
  reason: z.string().trim().min(5),
  startsAt: z.string().min(1),
});

function RescheduleDialog({
  iv,
  open,
  onOpenChange,
}: {
  iv: Interview;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("interviews.manage");
  const ids = { reason: useId(), when: useId() };
  const form = useForm<z.infer<typeof rescheduleSchema>>({
    resolver: zodResolver(rescheduleSchema),
    defaultValues: { reason: "", startsAt: "" },
  });
  const [formError, setFormError] = useState<string | null>(null);
  const move = useInterviewMutation<{ reason: string; starts_at: string }, Scheduled>(
    () => `/hr/interviews/${iv.id}/reschedule/`,
  );
  const submit = form.handleSubmit((values) =>
    move.mutate(
      { reason: values.reason, starts_at: fromLocalInput(values.startsAt) },
      {
        onSuccess: () => onOpenChange(false),
        onError: (err) =>
          setFormError(
            applyServerErrors(err, form.setError, { reason: "reason", starts_at: "startsAt" }),
          ),
      },
    ),
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("rescheduleTitle")}</DialogTitle>
          <DialogDescription>{t("rescheduleHelp")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-3" noValidate>
          <div className="flex flex-col gap-1">
            <Label htmlFor={ids.when}>{t("newTime")}</Label>
            <Input id={ids.when} type="datetime-local" {...form.register("startsAt")} />
            {form.formState.errors.startsAt ? (
              <p className="text-destructive text-xs">{t("timeRequired")}</p>
            ) : null}
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor={ids.reason}>{t("reason")}</Label>
            <Input id={ids.reason} {...form.register("reason")} />
            {form.formState.errors.reason ? (
              <p className="text-destructive text-xs">{t("reasonRequired")}</p>
            ) : null}
          </div>
          {formError ? (
            <p role="alert" className="text-destructive text-sm">
              {formError}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={move.isPending}>
              {t("reschedule")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------------------ scorecards
function ScorecardSection({ view }: { view: PanelView }) {
  const t = useTranslations("interviews.scorecard");
  const iv = view.interview;
  const cards = useScorecards(iv.id, view.on_panel || view.can_manage);
  if (!view.on_panel && !view.can_manage) return null;
  if (view.scorecard_criteria.length === 0)
    return (
      <section className="rounded-lg border p-4">
        <h2 className="text-lg font-semibold">{t("title")}</h2>
        <p className="text-muted-foreground text-sm">{t("noTemplate")}</p>
      </section>
    );
  const own = cards.data?.find((c) => c.own);
  const others = (cards.data ?? []).filter((c) => !c.own);
  return (
    <section aria-labelledby="iv-score" className="flex flex-col gap-3 rounded-lg border p-4">
      <h2 id="iv-score" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-xs">{t("independent")}</p>
      {cards.isPending ? (
        <PageSkeleton />
      ) : cards.isError ? (
        <ErrorState error={cards.error} onRetry={() => cards.refetch()} />
      ) : (
        <>
          {view.on_panel ? (
            own?.submitted_at ? (
              <SubmittedCard card={own} criteria={view.scorecard_criteria} />
            ) : (
              <ScorecardForm view={view} draft={own} />
            )
          ) : null}
          {others.map((c) => (
            <SubmittedCard key={c.id} card={c} criteria={view.scorecard_criteria} />
          ))}
        </>
      )}
    </section>
  );
}

const scorecardSchema = z.object({
  scores: z.record(z.string(), z.number().int().min(1).max(5).nullable()),
  notes: z.record(z.string(), z.string().max(2000)),
  overall: z.number().int().min(1).max(5).nullable(),
  recommendation: z.string(),
  summary: z.string().max(4000),
});
type ScoreValues = z.infer<typeof scorecardSchema>;

function ScorecardForm({ view, draft }: { view: PanelView; draft: Scorecard | undefined }) {
  const t = useTranslations("interviews.scorecard");
  const iv = view.interview;
  const criteria = view.scorecard_criteria;
  const form = useForm<ScoreValues>({
    resolver: zodResolver(scorecardSchema),
    defaultValues: {
      scores: Object.fromEntries(criteria.map((c) => [c.key, draft?.scores[c.key] ?? null])),
      notes: Object.fromEntries(criteria.map((c) => [c.key, draft?.criterion_notes[c.key] ?? ""])),
      overall: draft?.overall ?? null,
      recommendation: draft?.recommendation ?? "",
      summary: draft?.notes ?? "",
    },
  });
  const scores = useWatch({ control: form.control, name: "scores" });
  const overall = useWatch({ control: form.control, name: "overall" });
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const save = useInterviewMutation<ScorecardInput, Scorecard>(
    () => `/hr/interviews/${iv.id}/scorecard/`,
    "put",
  );
  const submit = useInterviewMutation<ScorecardInput, Scorecard>(
    () => `/hr/interviews/${iv.id}/scorecard/submit/`,
  );
  const started = iv.starts_at ? new Date(iv.starts_at) <= new Date() : false;
  const payload = (v: ScoreValues): ScorecardInput => ({
    scores: Object.fromEntries(
      Object.entries(v.scores).filter((e): e is [string, number] => e[1] !== null),
    ),
    criterion_notes: v.notes,
    overall: v.overall,
    recommendation: (v.recommendation || "") as ScorecardInput["recommendation"],
    notes: v.summary,
  });
  const onError = (err: unknown) => setFormError(applyServerErrors(err, form.setError));
  return (
    <form
      className="flex flex-col gap-3"
      noValidate
      onSubmit={form.handleSubmit((v) => submit.mutate(payload(v), { onError }))}
    >
      {criteria.map((c) => (
        <fieldset key={c.key} className="rounded border p-3">
          <legend className="px-1 font-medium">{c.title}</legend>
          {c.description ? <p className="text-muted-foreground text-xs">{c.description}</p> : null}
          <RatingInput
            label={t("rating", { title: c.title })}
            value={scores[c.key] ?? null}
            onChange={(n) => form.setValue(`scores.${c.key}`, n, { shouldDirty: true })}
          />
          <Label className="mt-2 block text-xs" htmlFor={`note-${c.key}`}>
            {t("evidence")}
          </Label>
          <textarea
            id={`note-${c.key}`}
            className="mt-1 w-full rounded border p-2 text-sm"
            rows={2}
            {...form.register(`notes.${c.key}`)}
          />
        </fieldset>
      ))}
      <RatingInput
        label={t("overall")}
        value={overall}
        onChange={(n) => form.setValue("overall", n, { shouldDirty: true })}
      />
      <fieldset>
        <legend className="text-sm font-medium">{t("recommendation")}</legend>
        <div className="mt-1 flex flex-wrap gap-2">
          {RECOMMENDATIONS.map((r) => (
            <label key={r} className="flex items-center gap-1 text-sm">
              <input type="radio" value={r} {...form.register("recommendation")} />
              {t(`rec.${r}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <Label htmlFor={`summary-${iv.id}`}>{t("summary")}</Label>
      <textarea
        id={`summary-${iv.id}`}
        className="w-full rounded border p-2 text-sm"
        rows={3}
        {...form.register("summary")}
      />
      {formError ? (
        <p role="alert" className="text-destructive text-sm">
          {formError}
        </p>
      ) : null}
      {saved ? (
        <p role="status" className="text-muted-foreground text-xs">
          {t("saved")}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={save.isPending}
          onClick={() =>
            save.mutate(payload(form.getValues()), {
              onSuccess: () => setSaved(true),
              onError,
            })
          }
        >
          {t("saveDraft")}
        </Button>
        <Button type="submit" disabled={submit.isPending || !started}>
          {t("submit")}
        </Button>
        {!started ? <p className="text-muted-foreground text-xs">{t("afterStart")}</p> : null}
      </div>
    </form>
  );
}

function RatingInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (n: number) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="mt-1 flex gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${label}: ${n}`}
          onClick={() => onChange(n)}
          className={`h-8 w-8 rounded border text-sm ${value === n ? "bg-primary text-primary-foreground" : ""}`}
        >
          {n}
        </button>
      ))}
    </div>
  );
}

function SubmittedCard({
  card,
  criteria,
}: {
  card: Scorecard;
  criteria: PanelView["scorecard_criteria"];
}) {
  const t = useTranslations("interviews.scorecard");
  return (
    <article className="rounded border p-3" aria-label={t("cardOf", { name: card.panelist })}>
      <h3 className="font-medium">
        {card.panelist}
        {card.own ? ` (${t("you")})` : ""}
        {card.submitted_at ? "" : ` · ${t("draft")}`}
      </h3>
      <ul className="mt-1 grid gap-1 text-sm sm:grid-cols-2">
        {criteria.map((c) => (
          <li key={c.key}>
            {c.title}: <span className="font-semibold">{card.scores[c.key] ?? "-"}</span>
            {card.criterion_notes[c.key] ? (
              <span className="text-muted-foreground"> — {card.criterion_notes[c.key]}</span>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="mt-1 text-sm">
        {t("overall")}: <span className="font-semibold">{card.overall ?? "-"}</span>
        {card.recommendation ? ` · ${t(`rec.${card.recommendation}`)}` : ""}
      </p>
      {card.notes ? <p className="text-muted-foreground mt-1 text-sm">{card.notes}</p> : null}
    </article>
  );
}

function FeedbackSection({ id }: { id: string }) {
  const t = useTranslations("interviews.feedback");
  const tr = useTranslations("interviews.scorecard");
  const fb = useFeedback(id, true);
  return (
    <section aria-labelledby="iv-fb" className="flex flex-col gap-2 rounded-lg border p-4">
      <h2 id="iv-fb" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-xs">{t("help")}</p>
      {fb.isPending ? (
        <PageSkeleton />
      ) : fb.isError ? (
        <ErrorState error={fb.error} onRetry={() => fb.refetch()} />
      ) : (
        <>
          <p className="text-sm">
            {t("submitted", { submitted: fb.data.submitted, total: fb.data.panel_size })}
            {fb.data.outstanding.length
              ? ` · ${t("waiting", { names: fb.data.outstanding.map((o) => o.name).join(", ") })}`
              : ""}
          </p>
          {fb.data.submitted > 0 ? (
            <table className="text-sm">
              <caption className="sr-only">{t("title")}</caption>
              <thead>
                <tr>
                  <th className="text-left">{t("criterion")}</th>
                  <th>{t("average")}</th>
                  <th>{t("range")}</th>
                </tr>
              </thead>
              <tbody>
                {fb.data.criteria.map((c) => (
                  <tr key={c.key}>
                    <td>
                      {c.title}
                      {c.disagreement ? (
                        <Badge variant="outline" className="ml-2">
                          {t("disagreement")}
                        </Badge>
                      ) : null}
                    </td>
                    <td className="text-center">{c.average ?? "-"}</td>
                    <td className="text-center">{c.count ? `${c.min}–${c.max}` : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          <p className="text-sm">
            {t("overallAverage")}:{" "}
            <span className="font-semibold">{fb.data.overall_average ?? "-"}</span>
            {" · "}
            {RECOMMENDATIONS.map(
              (r) => `${tr(`rec.${r}`)} ${fb.data.recommendations[r] ?? 0}`,
            ).join(", ")}
          </p>
        </>
      )}
    </section>
  );
}

// ------------------------------------------------------------------------------ application panel
export function ApplicationInterviewsPanel({
  applicationId,
  jobId,
  status,
}: {
  applicationId: string;
  jobId: string;
  status: string;
}) {
  const t = useTranslations("interviews.panelSection");
  const { role } = useJobsContext();
  const format = useFormatter();
  const canManage = !!role && MANAGERS.includes(role);
  const schedulable = status === "shortlisted" || status === "interview";
  const rows = useApplicationInterviews(applicationId, schedulable || status === "offer");
  const [open, setOpen] = useState(false);
  if (!schedulable && (rows.data?.length ?? 0) === 0) return null;
  return (
    <section
      id="interviews"
      aria-labelledby="hr-interviews"
      className="flex flex-col gap-2 rounded-lg border p-4"
    >
      <h2 id="hr-interviews" className="text-lg font-semibold">
        {t("title")}
      </h2>
      {rows.isPending ? null : rows.isError ? (
        <ErrorState error={rows.error} onRetry={() => rows.refetch()} />
      ) : rows.data.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("none")}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {rows.data.map((iv) => (
            <li key={iv.id}>
              <Link href={`/hr/interviews/${iv.id}`} className="underline">
                {iv.stage}
              </Link>{" "}
              ·{" "}
              {iv.starts_at
                ? format.dateTime(new Date(iv.starts_at), {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })
                : t("awaiting")}
              {" · "}
              {t(`status.${iv.status}`)}
            </li>
          ))}
        </ul>
      )}
      {canManage && schedulable ? (
        <>
          <Button size="sm" className="self-start" onClick={() => setOpen(true)}>
            {t("schedule")}
          </Button>
          <ScheduleDialog
            applicationId={applicationId}
            jobId={jobId}
            open={open}
            onOpenChange={setOpen}
          />
        </>
      ) : null}
    </section>
  );
}

const scheduleSchema = z
  .object({
    stage: z.string().trim().min(1).max(60),
    mode: z.enum(MODES),
    location: z.string().max(300),
    videoLink: z.union([z.literal(""), z.url()]),
    durationMinutes: z.number().int().min(5).max(480),
    timing: z.enum(["fixed", "slots"]),
    startsAt: z.string(),
    slots: z.array(z.object({ value: z.string() })),
    panel: z.array(z.string()).min(1),
    lead: z.string(),
    templateId: z.string(),
    instructions: z.string().max(2000),
  })
  .refine((v) => (v.timing === "fixed" ? v.startsAt !== "" : v.slots.some((s) => s.value !== "")), {
    path: ["startsAt"],
    message: "time",
  })
  .refine((v) => v.mode !== "in_person" || v.location.trim() !== "", {
    path: ["location"],
    message: "location",
  });
type ScheduleValues = z.infer<typeof scheduleSchema>;

function ScheduleDialog({
  applicationId,
  jobId,
  open,
  onOpenChange,
}: {
  applicationId: string;
  jobId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("interviews.schedule");
  const tm = useTranslations("interviews.mode");
  const options = usePanelOptions(open);
  const templates = useTemplates(jobId, open);
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "Africa/Harare";
  const form = useForm<ScheduleValues>({
    resolver: zodResolver(scheduleSchema),
    defaultValues: {
      stage: "",
      mode: "video",
      location: "",
      videoLink: "",
      durationMinutes: 45,
      timing: "fixed",
      startsAt: "",
      slots: [{ value: "" }, { value: "" }],
      panel: [],
      lead: "",
      templateId: "",
      instructions: "",
    },
  });
  const slots = useFieldArray({ control: form.control, name: "slots" });
  const [formError, setFormError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<Scheduled["conflicts"]>([]);
  const create = useInterviewMutation<Record<string, unknown>, Scheduled>(
    () => `/hr/applications/${applicationId}/interviews/`,
  );
  const createTemplate = useInterviewMutation<Record<string, unknown>, ScorecardTemplate>(
    () => `/hr/jobs/${jobId}/scorecard-templates/`,
  );
  const ids = {
    stage: useId(),
    mode: useId(),
    location: useId(),
    link: useId(),
    duration: useId(),
    when: useId(),
    template: useId(),
    instructions: useId(),
  };
  const timing = useWatch({ control: form.control, name: "timing" });
  const mode = useWatch({ control: form.control, name: "mode" });
  const panel = useWatch({ control: form.control, name: "panel" });
  const errors = form.formState.errors;

  const submit = form.handleSubmit((v) => {
    setFormError(null);
    const body = {
      stage: v.stage,
      mode: v.mode,
      location: v.location,
      video_link: v.videoLink,
      duration_minutes: v.durationMinutes,
      timezone: tz,
      instructions: v.instructions,
      scorecard_template_id: v.templateId || null,
      panel: v.panel.map((id) => ({
        membership_id: id,
        role: id === (v.lead || v.panel[0]) ? "lead" : "member",
      })),
      ...(v.timing === "fixed"
        ? { starts_at: fromLocalInput(v.startsAt) }
        : { slots: v.slots.filter((s) => s.value).map((s) => fromLocalInput(s.value)) }),
    };
    create.mutate(body, {
      onSuccess: (res) => {
        setConflicts(res.conflicts);
        if (res.conflicts.length === 0) onOpenChange(false);
      },
      onError: (err) =>
        setFormError(
          applyServerErrors(err, form.setError, {
            stage: "stage",
            location: "location",
            video_link: "videoLink",
            starts_at: "startsAt",
            panel: "panel",
          }),
        ),
    });
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("help", { tz })}</DialogDescription>
        </DialogHeader>
        {conflicts.length > 0 ? (
          <Alert>
            <AlertTitle>{t("conflictsTitle")}</AlertTitle>
            <AlertDescription>
              {t("conflicts", { count: conflicts.length })}
              <Button
                size="sm"
                variant="outline"
                className="mt-2"
                onClick={() => onOpenChange(false)}
              >
                {t("keepAnyway")}
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}
        <form onSubmit={submit} className="flex flex-col gap-3" noValidate>
          <div className="flex flex-col gap-1">
            <Label htmlFor={ids.stage}>{t("stage")}</Label>
            <Input id={ids.stage} placeholder={t("stageHint")} {...form.register("stage")} />
            {errors.stage ? <p className="text-destructive text-xs">{t("stageRequired")}</p> : null}
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor={ids.mode}>{t("mode")}</Label>
            <select id={ids.mode} className="h-9 rounded border px-2" {...form.register("mode")}>
              {MODES.map((m) => (
                <option key={m} value={m}>
                  {tm(m)}
                </option>
              ))}
            </select>
          </div>
          {mode === "in_person" ? (
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.location}>{t("location")}</Label>
              <Input id={ids.location} {...form.register("location")} />
              {errors.location ? (
                <p className="text-destructive text-xs">{t("locationRequired")}</p>
              ) : null}
            </div>
          ) : null}
          {mode === "video" ? (
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.link}>{t("videoLink")}</Label>
              <Input id={ids.link} type="url" {...form.register("videoLink")} />
              {errors.videoLink ? (
                <p className="text-destructive text-xs">{t("linkInvalid")}</p>
              ) : null}
            </div>
          ) : null}
          <div className="flex flex-col gap-1">
            <Label htmlFor={ids.duration}>{t("duration")}</Label>
            <Input
              id={ids.duration}
              type="number"
              min={5}
              max={480}
              {...form.register("durationMinutes", { valueAsNumber: true })}
            />
          </div>
          <fieldset>
            <legend className="text-sm font-medium">{t("timing")}</legend>
            <label className="mr-4 text-sm">
              <input type="radio" value="fixed" {...form.register("timing")} /> {t("fixed")}
            </label>
            <label className="text-sm">
              <input type="radio" value="slots" {...form.register("timing")} /> {t("slots")}
            </label>
          </fieldset>
          {timing === "fixed" ? (
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.when}>{t("startsAt")}</Label>
              <Input id={ids.when} type="datetime-local" {...form.register("startsAt")} />
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {slots.fields.map((f, i) => (
                <div key={f.id} className="flex items-center gap-2">
                  <Label className="sr-only" htmlFor={`slot-${f.id}`}>
                    {t("slotN", { n: i + 1 })}
                  </Label>
                  <Input
                    id={`slot-${f.id}`}
                    type="datetime-local"
                    {...form.register(`slots.${i}.value`)}
                  />
                  <Button type="button" size="sm" variant="outline" onClick={() => slots.remove(i)}>
                    {t("removeSlot")}
                  </Button>
                </div>
              ))}
              {slots.fields.length < 12 ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="self-start"
                  onClick={() => slots.append({ value: "" })}
                >
                  {t("addSlot")}
                </Button>
              ) : null}
            </div>
          )}
          {errors.startsAt ? <p className="text-destructive text-xs">{t("timeRequired")}</p> : null}
          <fieldset className="flex flex-col gap-1">
            <legend className="text-sm font-medium">{t("panel")}</legend>
            {options.isPending ? (
              <p className="text-muted-foreground text-xs">{t("loading")}</p>
            ) : options.isError ? (
              <p className="text-destructive text-xs">{t("panelFailed")}</p>
            ) : (
              options.data.map((m) => (
                <label key={m.membership_id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" value={m.membership_id} {...form.register("panel")} />
                  {m.name}
                  {panel.includes(m.membership_id) ? (
                    <span className="ml-2 text-xs">
                      <input
                        type="radio"
                        aria-label={t("leadOf", { name: m.name })}
                        value={m.membership_id}
                        {...form.register("lead")}
                      />{" "}
                      {t("lead")}
                    </span>
                  ) : null}
                </label>
              ))
            )}
            {errors.panel ? <p className="text-destructive text-xs">{t("panelRequired")}</p> : null}
          </fieldset>
          <div className="flex flex-col gap-1">
            <Label htmlFor={ids.template}>{t("template")}</Label>
            <div className="flex gap-2">
              <select
                id={ids.template}
                className="h-9 flex-1 rounded border px-2"
                {...form.register("templateId")}
              >
                <option value="">{t("noTemplate")}</option>
                {(templates.data ?? []).map((tp) => (
                  <option key={tp.id} value={tp.id}>
                    {tp.name}
                  </option>
                ))}
              </select>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={createTemplate.isPending}
                onClick={() =>
                  createTemplate.mutate(
                    { extra_competencies: ["Communication"] },
                    { onSuccess: (tp) => form.setValue("templateId", tp.id) },
                  )
                }
              >
                {t("createTemplate")}
              </Button>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor={ids.instructions}>{t("instructions")}</Label>
            <textarea
              id={ids.instructions}
              className="rounded border p-2 text-sm"
              rows={2}
              {...form.register("instructions")}
            />
          </div>
          {formError ? (
            <p role="alert" className="text-destructive text-sm">
              {formError}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {t("send")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
