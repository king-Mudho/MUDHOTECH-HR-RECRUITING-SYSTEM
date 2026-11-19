"use client";

import { useQuery } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";

import { ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Badge } from "@/components/ui/badge";
import { useJobsContext } from "@/features/jobs/hooks";
import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

export type BillingOverview = components["schemas"]["BillingOverview"];
type UsageMetric = components["schemas"]["UsageMetric"];

export const BILLING_VIEWERS = ["org_admin"];
export const billingKey = (orgId: string) => ["billing", orgId] as const;

/** Share of the limit used, 0-1 (null when unlimited). */
export function usageShare(m: Pick<UsageMetric, "used" | "limit">): number | null {
  if (m.limit === null || m.limit === undefined) return null;
  if (m.limit <= 0) return 1;
  return Math.min(1, m.used / m.limit);
}

export function useBilling() {
  const { orgId, role } = useJobsContext();
  return useQuery({
    queryKey: billingKey(orgId ?? ""),
    queryFn: () => api.get<BillingOverview>("/hr/billing/", { orgId: orgId! }),
    enabled: !!orgId && !!role && BILLING_VIEWERS.includes(role),
  });
}

export function BillingUsage({ data }: { data: BillingOverview }) {
  const t = useTranslations("billing");
  const format = useFormatter();
  const limited = data.usage.filter((m) => m.limit !== null || m.metric === "applications_month");
  return (
    <section aria-labelledby="usage" className="flex flex-col gap-3 rounded-lg border p-4">
      <h2 id="usage" className="text-lg font-semibold">
        {t("usage.title")}
      </h2>
      <ul className="flex flex-col gap-3 text-sm">
        {limited.map((m) => {
          const share = usageShare(m);
          const used = m.metric === "storage_gb" ? `${m.used} GB` : format.number(m.used);
          return (
            <li key={m.metric} className="flex flex-col gap-1">
              <div className="flex flex-wrap justify-between gap-2">
                <span>{t.has(`metrics.${m.metric}`) ? t(`metrics.${m.metric}`) : m.label}</span>
                <span className="tabular-nums">
                  {m.limit === null || m.limit === undefined
                    ? t("usage.unlimited", { used })
                    : t("usage.of", { used, limit: m.limit })}
                </span>
              </div>
              {share !== null ? (
                <div
                  role="meter"
                  aria-label={t.has(`metrics.${m.metric}`) ? t(`metrics.${m.metric}`) : m.label}
                  aria-valuemin={0}
                  aria-valuemax={m.limit ?? 0}
                  aria-valuenow={m.used}
                  className="bg-muted h-2 overflow-hidden rounded"
                >
                  <div
                    className={share >= 1 ? "bg-destructive h-2" : "bg-primary h-2"}
                    style={{ width: `${share * 100}%` }}
                  />
                </div>
              ) : null}
              {share !== null && share >= 1 ? (
                <p className="text-destructive text-xs">{t("usage.full")}</p>
              ) : null}
            </li>
          );
        })}
      </ul>
      {data.history.length ? (
        <details className="text-sm">
          <summary className="cursor-pointer">{t("usage.history")}</summary>
          <table className="mt-2 w-full">
            <caption className="sr-only">{t("usage.history")}</caption>
            <thead>
              <tr className="text-muted-foreground text-left text-xs">
                <th scope="col">{t("usage.month")}</th>
                <th scope="col">{t("metrics.applications_month")}</th>
                <th scope="col">{t("metrics.ai_evaluations_month")}</th>
                <th scope="col">{t("metrics.active_vacancies")}</th>
              </tr>
            </thead>
            <tbody>
              {data.history.map((h) => (
                <tr key={h.period} className="border-t">
                  <th scope="row" className="py-1 text-left font-normal">
                    {format.dateTime(new Date(`${h.period}T00:00:00`), {
                      month: "long",
                      year: "numeric",
                    })}
                  </th>
                  <td className="tabular-nums">{h.values.applications_month ?? 0}</td>
                  <td className="tabular-nums">{h.values.ai_evaluations_month ?? 0}</td>
                  <td className="tabular-nums">{h.values.active_vacancies ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}
    </section>
  );
}

export function BillingPlanCard({ data }: { data: BillingOverview }) {
  const t = useTranslations("billing");
  const format = useFormatter();
  const s = data.subscription;
  const date = (iso: string | null | undefined) =>
    iso ? format.dateTime(new Date(iso), { dateStyle: "long" }) : "";
  return (
    <section aria-labelledby="plan" className="flex flex-col gap-2 rounded-lg border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="plan" className="text-lg font-semibold">
          {t("plan.title", { name: data.plan.name })}
        </h2>
        <Badge
          variant={s.status === "active" || s.status === "trialing" ? "outline" : "destructive"}
        >
          {t.has(`status.${s.status}`) ? t(`status.${s.status}`) : s.status}
        </Badge>
      </div>
      {s.status === "trialing" && s.trial_ends_at ? (
        <p className="text-sm">{t("plan.trialEnds", { date: date(s.trial_ends_at) })}</p>
      ) : null}
      {s.status === "active" && s.current_period_end ? (
        <p className="text-sm">{t("plan.renews", { date: date(s.current_period_end) })}</p>
      ) : null}
      {s.status === "past_due" && s.grace_until ? (
        <p className="text-destructive text-sm" role="alert">
          {t("plan.grace", { date: date(s.grace_until) })}
        </p>
      ) : null}
      {s.status === "read_only" ? (
        <p className="text-destructive text-sm" role="alert">
          {t("plan.readOnly")}
        </p>
      ) : null}
    </section>
  );
}

export function BillingRoute() {
  const t = useTranslations("billing");
  const { role, isPending } = useJobsContext();
  const billing = useBilling();
  if (isPending) return <PageSkeleton />;
  if (!role || !BILLING_VIEWERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  if (billing.isPending) return <PageSkeleton />;
  if (billing.isError)
    return <ErrorState error={billing.error} onRetry={() => billing.refetch()} />;
  return (
    <div className="flex flex-col gap-4">
      <BillingPlanCard data={billing.data} />
      <BillingUsage data={billing.data} />
    </div>
  );
}
