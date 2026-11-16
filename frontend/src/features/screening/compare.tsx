"use client";

import { useQueries } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { APPLICATION_VIEWERS, type HRApplicationDetail } from "@/features/hr-applications/api";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api } from "@/lib/api-client";

import type { CriterionResult, Evaluation } from "./api";
import { AiNotice, BandBadge } from "./components";

export const MAX_COMPARE = 4;

type Column = { app: HRApplicationDetail; evaluation: Evaluation | null };

function Cell({ result }: { result: CriterionResult | undefined }) {
  const t = useTranslations("screening.compare");
  const ts = useTranslations("screening.status");
  if (!result) return <span className="text-muted-foreground">—</span>;
  const snippets = result.evidence.map((e) => e.snippet).filter(Boolean);
  return (
    <div className="flex flex-col gap-1">
      <span className="font-medium">
        {result.score === null ? t("unknown") : t("score", { score: result.score })}
      </span>
      <span className="text-muted-foreground text-xs">
        {ts.has(result.evidence_status) ? ts(result.evidence_status) : result.evidence_status}
      </span>
      {snippets.length ? (
        <details className="text-xs">
          <summary className="cursor-pointer underline">
            {t("evidence", { count: snippets.length })}
          </summary>
          <ul className="mt-1 flex flex-col gap-1">
            {snippets.map((s, i) => (
              <li key={i} className="text-muted-foreground border-l-2 pl-2">
                “{s}”
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

/** Side-by-side comparison of up to four applicants (FR-M12-03). */
export function CompareView({ ids }: { ids: string[] }) {
  const t = useTranslations("screening.compare");
  const { orgId, role, isPending } = useJobsContext();
  const chosen = ids.slice(0, MAX_COMPARE);
  const queries = useQueries({
    queries: chosen.map((id) => ({
      queryKey: ["hr-applications", orgId ?? "", id, "compare"],
      queryFn: async (): Promise<Column> => {
        const app = await api.get<HRApplicationDetail>(`/hr/applications/${id}/`, {
          orgId: orgId!,
        });
        let evaluation: Evaluation | null = null;
        try {
          evaluation = await api.get<Evaluation>(`/hr/applications/${id}/evaluation/`, {
            orgId: orgId!,
          });
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 404)) throw err;
        }
        return { app, evaluation };
      },
      enabled: !!orgId,
    })),
  });

  if (isPending) return <PageSkeleton />;
  if (!orgId || !role || !APPLICATION_VIEWERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  if (chosen.length < 2) return <ForbiddenState title={t("pickTitle")} description={t("pick")} />;
  const failed = queries.find((q) => q.isError);
  if (failed) return <ErrorState error={failed.error} onRetry={() => failed.refetch()} />;
  if (queries.some((q) => q.isPending)) return <PageSkeleton />;
  const columns = queries.map((q) => q.data!);
  const criteria = new Map<string, { title: string; importance: string }>();
  for (const c of columns)
    for (const r of c.evaluation?.criteria ?? [])
      if (!criteria.has(r.criterion_id))
        criteria.set(r.criterion_id, { title: r.title, importance: r.importance });
  const manual = (c: Column) => c.evaluation?.band === "manual_review_requested";

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">{t("title", { count: columns.length })}</h1>
        <AiNotice />
        {ids.length > MAX_COMPARE ? (
          <p role="status" className="text-sm">
            {t("limit", { max: MAX_COMPARE })}
          </p>
        ) : null}
      </div>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <caption className="sr-only">{t("caption")}</caption>
          <thead className="bg-muted/50 text-left">
            <tr>
              <th scope="col" className="px-3 py-2">
                {t("criterion")}
              </th>
              {columns.map((c) => (
                <th key={c.app.id} scope="col" className="px-3 py-2 align-top">
                  <Link href={`/hr/applications/${c.app.id}`} className="underline">
                    {c.app.candidate_name || c.app.reference}
                  </Link>
                  <div className="mt-1 flex flex-wrap gap-1 font-normal">
                    {c.evaluation && !manual(c) ? <BandBadge band={c.evaluation.band} /> : null}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-t">
              <th scope="row" className="px-3 py-2 text-left font-medium">
                {t("total")}
              </th>
              {columns.map((c) => (
                <td key={c.app.id} className="px-3 py-2">
                  {manual(c)
                    ? t("manual")
                    : c.evaluation?.total_score == null
                      ? "—"
                      : t("score", { score: c.evaluation.total_score })}
                  {c.evaluation?.coverage != null && !manual(c) ? (
                    <span className="text-muted-foreground text-xs">
                      {" "}
                      · {t("coverage", { value: Math.round(c.evaluation.coverage * 100) })}
                    </span>
                  ) : null}
                </td>
              ))}
            </tr>
            {[...criteria.entries()].map(([id, meta]) => (
              <tr key={id} className="border-t align-top">
                <th scope="row" className="px-3 py-2 text-left font-medium">
                  {meta.title}
                  {meta.importance === "essential" ? (
                    <span className="text-muted-foreground block text-xs">{t("essential")}</span>
                  ) : null}
                </th>
                {columns.map((c) => (
                  <td key={c.app.id} className="px-3 py-2">
                    {manual(c) ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      <Cell result={c.evaluation?.criteria.find((r) => r.criterion_id === id)} />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function CompareRoute() {
  const params = useSearchParams();
  const ids = (params.get("ids") ?? "").split(",").filter(Boolean);
  return <CompareView ids={ids} />;
}
