"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState, type FormEvent, type ReactNode } from "react";

import { ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useJobs, useJobsContext } from "@/features/jobs/hooks";
import { useDepartments } from "@/features/organisations/hooks";
import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

import { ExportPanel } from "./exports";

type Report = components["schemas"]["RecruitmentReport"];
type Duration = components["schemas"]["DurationStats"];

export const REPORT_VIEWERS = ["org_admin", "hr_manager"];

export interface ReportFilters {
  from: string;
  to: string;
  department: string;
  job: string;
}

export const EMPTY_FILTERS: ReportFilters = { from: "", to: "", department: "", job: "" };

export function reportQuery(f: ReportFilters): Record<string, string | undefined> {
  return {
    from: f.from || undefined,
    to: f.to || undefined,
    department: f.department || undefined,
    job: f.job || undefined,
  };
}

/** "3.5 h" under two days, "2.1 d" from two days on; em dash when there is no data. */
export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "—";
  if (hours < 48) return `${Math.round(hours * 10) / 10} h`;
  return `${Math.round((hours / 24) * 10) / 10} d`;
}

export function percent(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return "—";
  return `${Math.round(rate * 1000) / 10}%`;
}

const reportKey = (orgId: string, f: ReportFilters) => ["reports", orgId, f] as const;

export function ReportsRoute() {
  const t = useTranslations("reports");
  const { orgId, role, isPending } = useJobsContext();
  const [draft, setDraft] = useState<ReportFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<ReportFilters>(EMPTY_FILTERS);
  const client = useQueryClient();
  const allowed = !!role && REPORT_VIEWERS.includes(role);
  const report = useQuery({
    queryKey: reportKey(orgId ?? "", filters),
    queryFn: () =>
      api.get<Report>("/hr/reports/recruitment/", {
        orgId: orgId!,
        query: reportQuery(filters),
      }),
    enabled: !!orgId && allowed,
  });
  const refresh = useMutation({
    mutationFn: () => api.post<Report>("/hr/reports/recruitment/refresh/", {}, { orgId: orgId! }),
    onSuccess: (data) => client.setQueryData(reportKey(orgId ?? "", EMPTY_FILTERS), data),
  });
  if (isPending) return <PageSkeleton />;
  if (!allowed) return <ForbiddenState description={t("forbidden")} />;
  const apply = (next: ReportFilters) => {
    setDraft(next);
    setFilters(next);
  };
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t("title")}</h1>
          <p className="text-muted-foreground text-sm">{t("intro")}</p>
        </div>
        <Button
          variant="outline"
          disabled={refresh.isPending}
          onClick={() => {
            apply(EMPTY_FILTERS);
            refresh.mutate();
          }}
        >
          {refresh.isPending ? t("refreshing") : t("refresh")}
        </Button>
      </div>
      <Filters
        draft={draft}
        onChange={setDraft}
        onSubmit={() => setFilters(draft)}
        onReset={() => apply(EMPTY_FILTERS)}
      />
      <ExportPanel filters={filters} />
      {report.isPending ? (
        <PageSkeleton />
      ) : report.isError ? (
        <ErrorState error={report.error} onRetry={() => report.refetch()} />
      ) : (
        <ReportBody
          report={report.data}
          onDrill={(job) => apply({ ...filters, job })}
          jobSelected={!!filters.job}
        />
      )}
    </div>
  );
}

function Filters({
  draft,
  onChange,
  onSubmit,
  onReset,
}: {
  draft: ReportFilters;
  onChange: (f: ReportFilters) => void;
  onSubmit: () => void;
  onReset: () => void;
}) {
  const t = useTranslations("reports.filters");
  const { orgId } = useJobsContext();
  const departments = useDepartments(orgId ?? undefined);
  const jobs = useJobs({ ordering: "-created_at" });
  const ids = { from: useId(), to: useId(), dep: useId(), job: useId() };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit();
  };
  const select = "border-input bg-background h-10 rounded-md border px-2 text-sm";
  return (
    <form
      aria-label={t("label")}
      onSubmit={submit}
      className="grid gap-3 rounded-lg border p-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1.5fr_2fr_auto_auto] lg:items-end"
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={ids.from}>{t("from")}</Label>
        <Input
          id={ids.from}
          type="date"
          className="h-10"
          value={draft.from}
          onChange={(e) => onChange({ ...draft, from: e.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={ids.to}>{t("to")}</Label>
        <Input
          id={ids.to}
          type="date"
          className="h-10"
          value={draft.to}
          onChange={(e) => onChange({ ...draft, to: e.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={ids.dep}>{t("department")}</Label>
        <select
          id={ids.dep}
          className={select}
          value={draft.department}
          onChange={(e) => onChange({ ...draft, department: e.target.value })}
        >
          <option value="">{t("allDepartments")}</option>
          {(departments.data?.results ?? []).map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={ids.job}>{t("job")}</Label>
        <select
          id={ids.job}
          className={select}
          value={draft.job}
          onChange={(e) => onChange({ ...draft, job: e.target.value })}
        >
          <option value="">{t("allJobs")}</option>
          {(jobs.data?.results ?? []).map((j) => (
            <option key={j.id} value={j.id}>
              {j.title}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" className="h-10">
        {t("apply")}
      </Button>
      <Button type="button" variant="ghost" className="h-10" onClick={onReset}>
        {t("reset")}
      </Button>
    </form>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3 rounded-lg border p-4">
      <h2 id={id} className="text-lg font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border p-3">
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
      {hint ? <span className="text-muted-foreground text-xs">{hint}</span> : null}
    </div>
  );
}

/**
 * Horizontal bars inside a real table: the table is the accessible alternative by construction
 * (one series per chart, one theme hue, value always printed beside the bar).
 */
function BarTable({
  caption,
  rows,
  columns,
}: {
  caption: string;
  rows: { key: string; label: ReactNode; value: number; extra?: ReactNode[] }[];
  columns: { label: string; value: string; extra?: string[] };
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="text-muted-foreground text-left text-xs">
            <th scope="col" className="py-1 pr-2 font-normal">
              {columns.label}
            </th>
            <th scope="col" className="py-1 pr-2 font-normal">
              {columns.value}
            </th>
            {(columns.extra ?? []).map((c) => (
              <th key={c} scope="col" className="py-1 pr-2 text-right font-normal">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t">
              <th scope="row" className="w-40 py-1.5 pr-2 text-left font-normal">
                {r.label}
              </th>
              <td className="min-w-40 py-1.5 pr-2">
                <div className="flex items-center gap-2">
                  <div
                    className="bg-primary h-3 rounded-r"
                    style={{ width: `${(r.value / max) * 100}%`, minWidth: r.value ? 4 : 0 }}
                    title={`${r.value}`}
                    aria-hidden="true"
                  />
                  <span className="tabular-nums">{r.value}</span>
                </div>
              </td>
              {(r.extra ?? []).map((cell, i) => (
                <td key={i} className="py-1.5 pr-2 text-right tabular-nums">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportBody({
  report: r,
  onDrill,
  jobSelected,
}: {
  report: Report;
  onDrill: (job: string) => void;
  jobSelected: boolean;
}) {
  const t = useTranslations("reports");
  const format = useFormatter();
  const { data: jobs } = useJobs({ ordering: "-created_at" });
  const jobTitle = (id: string) => jobs?.results.find((j) => j.id === id)?.title ?? t("vacancy");
  const durationHint = (d: Duration) =>
    d.count ? t("durationHint", { count: d.count, p90: formatHours(d.p90_hours) }) : t("noData");
  return (
    <div className="flex flex-col gap-6">
      <p className="text-muted-foreground text-xs" aria-live="polite">
        {t("scope", {
          from: r.scope.from,
          to: r.scope.to,
          count: r.applications,
          when: format.dateTime(new Date(r.computed_at), {
            dateStyle: "medium",
            timeStyle: "short",
          }),
        })}{" "}
        {r.origin === "snapshot" ? t("fromSnapshot") : null}
      </p>

      <Section id="timing" title={t("timing.title")}>
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile
            label={t("timing.review")}
            value={formatHours(r.timing.time_to_review.median_hours)}
            hint={durationHint(r.timing.time_to_review)}
          />
          <Tile
            label={t("timing.shortlist")}
            value={formatHours(r.timing.time_to_shortlist.median_hours)}
            hint={durationHint(r.timing.time_to_shortlist)}
          />
          <Tile
            label={t("timing.hire")}
            value={formatHours(r.timing.time_to_hire.median_hours)}
            hint={durationHint(r.timing.time_to_hire)}
          />
        </div>
      </Section>

      <Section id="funnel" title={t("funnel.title")}>
        <BarTable
          caption={t("funnel.caption")}
          columns={{
            label: t("funnel.stage"),
            value: t("funnel.reached"),
            extra: [t("funnel.conversion")],
          }}
          rows={r.funnel.stages.map((s) => ({
            key: s.stage,
            label: t(`funnel.stages.${s.stage}`),
            value: s.count,
            extra: [percent(s.conversion)],
          }))}
        />
        <p className="text-muted-foreground text-xs">
          {t("funnel.withdrawn", { count: r.funnel.withdrawn })}
        </p>
      </Section>

      <Section id="sources" title={t("sources.title")}>
        {r.sources.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("noData")}</p>
        ) : (
          <BarTable
            caption={t("sources.caption")}
            columns={{
              label: t("sources.source"),
              value: t("sources.applications"),
              extra: [t("sources.shortlisted")],
            }}
            rows={r.sources.map((s) => ({
              key: s.source,
              label: s.source === "direct" ? t("sources.direct") : s.source,
              value: s.applications,
              extra: [s.shortlisted],
            }))}
          />
        )}
      </Section>

      <Section id="questionnaire" title={t("questionnaire.title")}>
        <p className="text-sm">
          {t("questionnaire.summary", {
            started: r.questionnaire.started,
            submitted: r.questionnaire.submitted,
            unfinished: r.questionnaire.unfinished,
          })}
        </p>
        <BarTable
          caption={t("questionnaire.stepsCaption")}
          columns={{ label: t("questionnaire.step"), value: t("questionnaire.unfinishedAt") }}
          rows={r.questionnaire.unfinished_by_step.map((s) => ({
            key: s.step,
            label: t(`questionnaire.steps.${s.step}`),
            value: s.unfinished,
          }))}
        />
        {jobSelected ? (
          r.questionnaire.questions.length ? (
            <BarTable
              caption={t("questionnaire.questionsCaption")}
              columns={{
                label: t("questionnaire.question"),
                value: t("questionnaire.answered"),
                extra: [t("questionnaire.dropOff")],
              }}
              rows={r.questionnaire.questions.map((q) => ({
                key: q.question_id,
                label: q.prompt,
                value: q.answered,
                extra: [percent(q.drop_off)],
              }))}
            />
          ) : (
            <p className="text-muted-foreground text-sm">{t("questionnaire.noQuestions")}</p>
          )
        ) : (
          <p className="text-muted-foreground text-xs">{t("questionnaire.pickJob")}</p>
        )}
      </Section>

      <Section id="ai" title={t("ai.title")}>
        <p className="text-muted-foreground text-xs">{t("ai.notice")}</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile
            label={t("ai.agreement")}
            value={percent(r.ai_agreement.agreement_rate)}
            hint={t("ai.decisions", { count: r.ai_agreement.decisions })}
          />
          <Tile label={t("ai.override")} value={percent(r.ai_agreement.override_rate)} />
          <Tile
            label={t("ai.claimOverride")}
            value={percent(r.ai_agreement.claim_verification_override_rate)}
          />
        </div>
        {r.ai_agreement.by_band.length ? (
          <BarTable
            caption={t("ai.byBandCaption")}
            columns={{
              label: t("ai.band"),
              value: t("ai.decisionsCol"),
              extra: [t("ai.overrides"), t("ai.overrideRate")],
            }}
            rows={r.ai_agreement.by_band.map((b) => ({
              key: b.band,
              label: t.has(`ai.bands.${b.band}`) ? t(`ai.bands.${b.band}`) : b.band,
              value: b.decisions,
              extra: [b.overrides, percent(b.override_rate)],
            }))}
          />
        ) : null}
        {r.ai_agreement.by_job.length > 1 || (!jobSelected && r.ai_agreement.by_job.length) ? (
          <BarTable
            caption={t("ai.byJobCaption")}
            columns={{
              label: t("vacancy"),
              value: t("ai.decisionsCol"),
              extra: [t("ai.overrideRate")],
            }}
            rows={r.ai_agreement.by_job.map((j) => ({
              key: j.job_id,
              label: (
                <button
                  type="button"
                  className="text-left underline underline-offset-2"
                  onClick={() => onDrill(j.job_id)}
                >
                  {jobTitle(j.job_id)}
                </button>
              ),
              value: j.decisions,
              extra: [
                <span key="rate">
                  {percent(j.override_rate)}
                  {(j.override_rate ?? 0) > 0.3 ? ` · ${t("ai.reviewRubric")}` : ""}
                </span>,
              ],
            }))}
          />
        ) : null}
      </Section>

      <Section id="processing" title={t("processing.title")}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile
            label={t("processing.failure")}
            value={percent(r.processing.parse_failure_rate)}
            hint={t("processing.runs", { count: r.processing.extraction_runs })}
          />
          <Tile label={t("processing.ocr")} value={percent(r.processing.ocr_rate)} />
          <Tile
            label={t("processing.extraction")}
            value={
              r.processing.mean_extraction_seconds === null
                ? "—"
                : `${Math.round(r.processing.mean_extraction_seconds)} s`
            }
          />
          <Tile
            label={t("processing.toEvaluation")}
            value={formatHours(r.processing.submission_to_evaluation.median_hours)}
          />
        </div>
      </Section>

      <Section id="clarifications" title={t("clarifications.title")}>
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile
            label={t("clarifications.responseRate")}
            value={percent(r.clarifications.response_rate)}
            hint={t("clarifications.counts", {
              answered: r.clarifications.answered,
              expired: r.clarifications.expired,
              open: r.clarifications.open,
            })}
          />
          <Tile
            label={t("clarifications.time")}
            value={formatHours(r.clarifications.time_to_answer.median_hours)}
          />
          <Tile label={t("clarifications.total")} value={`${r.clarifications.total}`} />
        </div>
      </Section>

      {jobSelected && r.scope.job ? (
        <p className="text-sm">
          <Link className="underline" href={`/hr/jobs/${r.scope.job}/applications`}>
            {t("openApplicants")}
          </Link>
        </p>
      ) : null}
    </div>
  );
}
