"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { APPLICATION_VIEWERS } from "@/features/hr-applications/api";
import { useJob, useJobsContext } from "@/features/jobs/hooks";
import { ApiError } from "@/lib/api-client";

import {
  BANDS,
  SCREENING_EDITORS,
  useRunFailures,
  useScreeningAnalytics,
  useScreeningRuns,
  useStartRun,
  type ScreeningAnalytics,
  type ScreeningRun,
} from "./api";
import { AiNotice } from "./components";

const SCOPES = ["pending", "all", "failed"] as const;

function StartRunForm({ jobId }: { jobId: string }) {
  const t = useTranslations("screening.start");
  const start = useStartRun(jobId);
  const [scope, setScope] = useState<(typeof SCOPES)[number]>("pending");
  const [newVersion, setNewVersion] = useState(false);
  const [reason, setReason] = useState("");
  const scopeId = useId();
  const reasonId = useId();
  const error =
    start.error instanceof ApiError ? start.error.message : start.error ? t("failed") : null;
  return (
    <form
      className="flex flex-col gap-3 rounded-lg border p-4"
      onSubmit={(e) => {
        e.preventDefault();
        start.mutate({ scope, use_current_version: newVersion, reason });
      }}
    >
      <h2 className="text-lg font-semibold">{t("title")}</h2>
      <div className="flex flex-col gap-1">
        <Label htmlFor={scopeId}>{t("scope")}</Label>
        <select
          id={scopeId}
          className="border-input h-9 rounded-md border bg-transparent px-2 text-sm"
          value={scope}
          onChange={(e) => setScope(e.target.value as (typeof SCOPES)[number])}
        >
          {SCOPES.map((s) => (
            <option key={s} value={s}>
              {t(`scopes.${s}`)}
            </option>
          ))}
        </select>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-4"
          checked={newVersion}
          onChange={(e) => setNewVersion(e.target.checked)}
        />
        {t("newVersion")}
      </label>
      {newVersion ? (
        <div className="flex flex-col gap-1">
          <Label htmlFor={reasonId}>{t("reason")}</Label>
          <Input
            id={reasonId}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            aria-describedby={`${reasonId}-hint`}
          />
          <p id={`${reasonId}-hint`} className="text-muted-foreground text-xs">
            {t("reasonHint")}
          </p>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      {start.isSuccess ? (
        <p role="status" className="text-muted-foreground text-sm">
          {t("started", { count: start.data.total })}
        </p>
      ) : null}
      <Button
        type="submit"
        className="self-start"
        disabled={start.isPending || (newVersion && reason.trim().length < 5)}
      >
        {start.isPending ? t("starting") : t("submit")}
      </Button>
    </form>
  );
}

function RunRow({ run, onFailures }: { run: ScreeningRun; onFailures: () => void }) {
  const t = useTranslations("screening.runs");
  const percent = Math.round(run.progress * 100);
  return (
    <li className="rounded-md border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{t(`status.${run.status}`)}</span>
        <span className="text-muted-foreground">
          {t("meta", { scope: run.scope, trigger: run.trigger, total: run.total })}
        </span>
        {run.failed ? (
          <Button size="sm" variant="outline" className="ml-auto" onClick={onFailures}>
            {t("showFailures", { count: run.failed })}
          </Button>
        ) : null}
      </div>
      <div
        className="bg-muted mt-2 h-2 w-full overflow-hidden rounded"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label={t("progress", { done: run.done, total: run.total })}
      >
        <div className="bg-primary h-full" style={{ width: `${percent}%` }} />
      </div>
      <p className="text-muted-foreground mt-1 text-xs">
        {t("progress", { done: run.done, total: run.total })}
      </p>
    </li>
  );
}

function Failures({ runId, jobId }: { runId: string; jobId: string }) {
  const t = useTranslations("screening.runs");
  const detail = useRunFailures(runId);
  const retry = useStartRun(jobId);
  if (detail.isPending) return <PageSkeleton rows={1} />;
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  return (
    <div className="rounded-md border p-3 text-sm">
      <h3 className="font-medium">{t("failuresTitle")}</h3>
      {detail.data.failures.length === 0 ? (
        <p className="text-muted-foreground">{t("noFailures")}</p>
      ) : (
        <>
          <ul className="mt-1 list-disc pl-5">
            {detail.data.failures.map((f) => (
              <li key={f.application_id}>
                <Link className="underline" href={`/hr/applications/${f.application_id}`}>
                  {t("failureLink")}
                </Link>
              </li>
            ))}
          </ul>
          <Button
            size="sm"
            className="mt-2"
            disabled={retry.isPending}
            onClick={() => retry.mutate({ scope: "failed" })}
          >
            {t("retryFailed")}
          </Button>
        </>
      )}
    </div>
  );
}

function Distribution({ data }: { data: ScreeningAnalytics }) {
  const t = useTranslations("screening.analytics");
  const tb = useTranslations("screening.bands");
  const max = Math.max(1, ...data.score_buckets.map((b) => b.count));
  const [table, setTable] = useState(false);
  const bands = BANDS.map((b) => ({
    band: b,
    count: data.bands.find((x) => x.band === b)?.count ?? 0,
  }));
  return (
    <section aria-labelledby="screening-distribution" className="rounded-lg border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="screening-distribution" className="text-lg font-semibold">
          {t("title")}
        </h2>
        <Button size="sm" variant="outline" onClick={() => setTable((v) => !v)}>
          {table ? t("showChart") : t("showTable")}
        </Button>
      </div>
      <AiNotice />
      <p className="mt-2 text-sm">
        {t("summary", { count: data.evaluated, median: data.median_score ?? "—" })}
      </p>
      {data.warnings.map((w) => (
        <Alert key={w.code} className="mt-2">
          <AlertTitle>{t(`warnings.${w.code}`)}</AlertTitle>
          <AlertDescription>{w.message}</AlertDescription>
        </Alert>
      ))}
      {table ? (
        <table className="mt-3 w-full text-sm">
          <caption className="sr-only">{t("tableCaption")}</caption>
          <thead>
            <tr>
              <th scope="col" className="text-left">
                {t("range")}
              </th>
              <th scope="col" className="text-right">
                {t("applications")}
              </th>
            </tr>
          </thead>
          <tbody>
            {data.score_buckets.map((b) => (
              <tr key={b.start}>
                <td>{t("rangeValue", { start: b.start, end: b.end })}</td>
                <td className="text-right">{b.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div
          className="mt-3 flex h-32 items-end gap-1"
          role="img"
          aria-label={t("chartAria", { count: data.evaluated })}
        >
          {data.score_buckets.map((b) => (
            <div key={b.start} className="flex flex-1 flex-col items-center gap-1">
              <div
                className="bg-primary w-full rounded-t"
                style={{ height: `${(b.count / max) * 100}%`, minHeight: b.count ? 2 : 0 }}
              />
              <span className="text-muted-foreground text-[10px]">{b.start}</span>
            </div>
          ))}
        </div>
      )}
      <ul className="mt-3 flex flex-wrap gap-3 text-sm">
        {bands.map((b) => (
          <li key={b.band}>
            {tb(b.band)}: <span className="font-medium">{b.count}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ScreeningView({ jobId }: { jobId: string }) {
  const t = useTranslations("screening");
  const { role, isPending, orgId } = useJobsContext();
  const job = useJob(jobId);
  const runs = useScreeningRuns(jobId);
  const analytics = useScreeningAnalytics(jobId);
  const [failuresOf, setFailuresOf] = useState<string | null>(null);

  if (isPending) return <PageSkeleton />;
  if (!orgId || !role || !APPLICATION_VIEWERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link href={`/hr/jobs/${jobId}`} className="text-sm underline">
          {t("backToJob")}
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">
          {t("title", { job: job.data?.title ?? "" })}
        </h1>
        <AiNotice />
      </div>
      {SCREENING_EDITORS.includes(role) ? <StartRunForm jobId={jobId} /> : null}
      {analytics.isPending ? (
        <PageSkeleton rows={2} />
      ) : analytics.isError ? (
        <ErrorState error={analytics.error} onRetry={() => analytics.refetch()} />
      ) : (
        <Distribution data={analytics.data} />
      )}
      <section aria-labelledby="screening-runs" className="flex flex-col gap-2">
        <h2 id="screening-runs" className="text-lg font-semibold">
          {t("runs.title")}
        </h2>
        {runs.isPending ? (
          <PageSkeleton rows={2} />
        ) : runs.isError ? (
          <ErrorState error={runs.error} onRetry={() => runs.refetch()} />
        ) : runs.data.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("runs.empty")}</p>
        ) : (
          <ul className="flex flex-col gap-2" aria-live="polite">
            {runs.data.map((r) => (
              <RunRow key={r.id} run={r} onFailures={() => setFailuresOf(r.id)} />
            ))}
          </ul>
        )}
        {failuresOf ? <Failures runId={failuresOf} jobId={jobId} /> : null}
      </section>
    </div>
  );
}

export function ScreeningRoute() {
  const { id } = useParams<{ id: string }>();
  return <ScreeningView jobId={id} />;
}
