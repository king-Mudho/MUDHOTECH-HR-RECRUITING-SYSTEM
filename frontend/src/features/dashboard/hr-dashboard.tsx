"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";

import { ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { APPLICATION_VIEWERS } from "@/features/hr-applications/api";
import { useJobs, useJobsContext } from "@/features/jobs/hooks";
import { BandBadge } from "@/features/screening/components";
import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

type Summary = components["schemas"]["DashboardSummary"];
type Funnel = components["schemas"]["Funnel"];

const CARDS = [
  "open_vacancies",
  "applications_today",
  "applications_7d",
  "processing_queue",
  "processing_errors",
  "pending_reviews",
  "clarifications_outstanding",
  "shortlist_approvals_pending",
] as const;

interface Filters {
  job?: string;
  from?: string;
  to?: string;
}

function useSummary(filters: Filters) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: ["hr-dashboard", orgId ?? "", filters],
    queryFn: () =>
      api.get<Summary>("/hr/dashboard/summary/", {
        orgId: orgId!,
        query: Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
      }),
    enabled: !!orgId,
  });
}

function FunnelChart({ jobId }: { jobId: string }) {
  const t = useTranslations("hrDashboard");
  const { orgId } = useJobsContext();
  const data = useQuery({
    queryKey: ["hr-dashboard", orgId ?? "", "funnel", jobId],
    queryFn: () => api.get<Funnel>(`/hr/jobs/${jobId}/funnel/`, { orgId: orgId! }),
    enabled: !!orgId,
  });
  if (data.isPending) return <PageSkeleton rows={1} />;
  if (data.isError) return <ErrorState error={data.error} onRetry={() => data.refetch()} />;
  const max = Math.max(1, ...data.data.stages.map((s) => s.count));
  return (
    <section aria-labelledby="funnel" className="rounded-lg border p-4">
      <h2 id="funnel" className="text-lg font-semibold">
        {t("funnel")}
      </h2>
      <table className="mt-2 w-full text-sm">
        <caption className="sr-only">{t("funnelCaption")}</caption>
        <tbody>
          {data.data.stages.map((s) => (
            <tr key={s.stage}>
              <th scope="row" className="w-32 py-1 text-left font-normal">
                {t(`stages.${s.stage}`)}
              </th>
              <td className="py-1">
                <div className="flex items-center gap-2">
                  <div
                    className="bg-primary h-3 rounded"
                    style={{ width: `${(s.count / max) * 100}%`, minWidth: s.count ? 4 : 0 }}
                    aria-hidden="true"
                  />
                  <span>{s.count}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-muted-foreground mt-1 text-xs">
        {t("withdrawn", { count: data.data.withdrawn })} ·{" "}
        {t("offersDeclined", { count: data.data.offers_declined })} ·{" "}
        {t("openingsFilled", {
          filled: data.data.openings.hired,
          total: data.data.openings.openings,
        })}
      </p>
    </section>
  );
}

export function HRDashboard() {
  const t = useTranslations("hrDashboard");
  const tb = useTranslations("screening.bands");
  const format = useFormatter();
  const { orgId, role, isPending } = useJobsContext();
  const [filters, setFilters] = useState<Filters>({});
  const id = useId();
  const jobs = useJobs({ status: "published" });
  const summary = useSummary(filters);
  if (isPending) return <PageSkeleton />;
  if (!orgId || !role || !APPLICATION_VIEWERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  const when = (iso: string | null | undefined) =>
    iso ? format.dateTime(new Date(iso), { dateStyle: "medium" }) : "—";

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <fieldset className="flex flex-wrap items-end gap-3">
        <legend className="sr-only">{t("filters")}</legend>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-job`}>{t("vacancy")}</Label>
          <select
            id={`${id}-job`}
            className="border-input h-9 rounded-md border bg-transparent px-2 text-sm"
            value={filters.job ?? ""}
            onChange={(e) => setFilters({ ...filters, job: e.target.value || undefined })}
          >
            <option value="">{t("allVacancies")}</option>
            {(jobs.data?.results ?? []).map((j) => (
              <option key={j.id} value={j.id}>
                {j.title}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-from`}>{t("from")}</Label>
          <Input
            id={`${id}-from`}
            type="date"
            className="h-9"
            value={filters.from ?? ""}
            onChange={(e) => setFilters({ ...filters, from: e.target.value || undefined })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${id}-to`}>{t("to")}</Label>
          <Input
            id={`${id}-to`}
            type="date"
            className="h-9"
            value={filters.to ?? ""}
            onChange={(e) => setFilters({ ...filters, to: e.target.value || undefined })}
          />
        </div>
      </fieldset>

      {summary.isPending ? (
        <PageSkeleton />
      ) : summary.isError ? (
        <ErrorState error={summary.error} onRetry={() => summary.refetch()} />
      ) : (
        <>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label={t("cardsLabel")}>
            {CARDS.map((key) => (
              <li key={key} className="rounded-lg border p-4">
                <p className="text-muted-foreground text-sm">{t(`cards.${key}`)}</p>
                <p className="text-2xl font-semibold">{summary.data.cards[key]}</p>
              </li>
            ))}
          </ul>

          <div className="grid gap-4 lg:grid-cols-2">
            <section aria-labelledby="ai-split" className="rounded-lg border p-4">
              <h2 id="ai-split" className="text-lg font-semibold">
                {t("aiTitle")}
              </h2>
              <p className="text-muted-foreground text-xs">
                {summary.data.ai_suggestions.ai_notice}
              </p>
              <ul className="mt-2 flex flex-col gap-1 text-sm">
                {Object.entries(summary.data.ai_suggestions.bands).map(([band, n]) => (
                  <li key={band} className="flex items-center justify-between gap-2">
                    <BandBadge band={band} />
                    <span>{n}</span>
                  </li>
                ))}
                {Object.keys(summary.data.ai_suggestions.bands).length === 0 ? (
                  <li className="text-muted-foreground">{t("none")}</li>
                ) : null}
              </ul>
            </section>
            <section aria-labelledby="human-split" className="rounded-lg border p-4">
              <h2 id="human-split" className="text-lg font-semibold">
                {t("humanTitle")}
              </h2>
              <p className="text-muted-foreground text-xs">{t("humanNote")}</p>
              <dl className="mt-2 grid grid-cols-[1fr_auto] gap-1 text-sm">
                {(["shortlisted", "not_selected", "on_hold"] as const).map((k) => (
                  <div key={k} className="contents">
                    <dt>{tb.has(k) ? tb(k) : t(`decisions.${k}`)}</dt>
                    <dd>{summary.data.human_decisions[k]}</dd>
                  </div>
                ))}
              </dl>
            </section>
          </div>

          {filters.job ? <FunnelChart jobId={filters.job} /> : null}

          <div className="grid gap-4 lg:grid-cols-2">
            {(["failed_processing", "pending_reviews"] as const).map((q) => (
              <section key={q} aria-labelledby={`q-${q}`} className="rounded-lg border p-4">
                <h2 id={`q-${q}`} className="text-lg font-semibold">
                  {t(`queues.${q}`)}
                </h2>
                {summary.data.queues[q].length === 0 ? (
                  <p className="text-muted-foreground mt-1 text-sm">{t("none")}</p>
                ) : (
                  <ul className="mt-2 flex flex-col gap-1 text-sm">
                    {summary.data.queues[q].map((r) => (
                      <li key={r.application_id} className="flex flex-wrap items-center gap-2">
                        <Link href={`/hr/applications/${r.application_id}`} className="underline">
                          {r.reference}
                        </Link>
                        <span className="text-muted-foreground">{r.job_title}</span>
                        <StatusBadge status={r.status} />
                        <span className="text-muted-foreground ml-auto text-xs">{when(r.at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
            <section aria-labelledby="q-approvals" className="rounded-lg border p-4">
              <h2 id="q-approvals" className="text-lg font-semibold">
                {t("queues.approvals")}
              </h2>
              {summary.data.queues.approvals.length === 0 ? (
                <p className="text-muted-foreground mt-1 text-sm">{t("none")}</p>
              ) : (
                <ul className="mt-2 flex flex-col gap-1 text-sm">
                  {summary.data.queues.approvals.map((a) => (
                    <li key={a.shortlist_id}>
                      <Link href={`/hr/jobs/${a.job_id}/shortlist`} className="underline">
                        {a.job_title}
                      </Link>{" "}
                      <span className="text-muted-foreground text-xs">{when(a.submitted_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section aria-labelledby="q-clar" className="rounded-lg border p-4">
              <h2 id="q-clar" className="text-lg font-semibold">
                {t("queues.clarifications_due")}
              </h2>
              {summary.data.queues.clarifications_due.length === 0 ? (
                <p className="text-muted-foreground mt-1 text-sm">{t("none")}</p>
              ) : (
                <ul className="mt-2 flex flex-col gap-1 text-sm">
                  {summary.data.queues.clarifications_due.map((c) => (
                    <li key={c.application_id}>
                      <Link href={`/hr/applications/${c.application_id}`} className="underline">
                        {c.job_title}
                      </Link>{" "}
                      <span className="text-muted-foreground text-xs">
                        {t("due", { when: when(c.due_at) })}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
