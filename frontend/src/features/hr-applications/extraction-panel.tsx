"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useJobsContext } from "@/features/jobs/hooks";
import { GROUPS, grouped } from "@/features/resumes/api";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

import { hrApplicationKeys, type HRApplicationDetail } from "./api";

type HRExtraction = components["schemas"]["HRExtraction"];
type HRClaim = components["schemas"]["HRClaim"];

const EDITORS = ["org_admin", "hr_manager", "recruiter"];
const READING = new Set(["pending", "running"]);
const FLAG_KEYS = [
  "identity_mismatch_possible",
  "duplicate_document_across_accounts",
  "injection_suspected",
  "hidden_text",
  "possibly_not_cv",
  "language_unsupported",
  "low_ocr_confidence",
  "ocr_unavailable",
  "garbled_text",
  "date_anomaly",
] as const;

export const extractionKeys = {
  panel: (orgId: string, id: string) => ["hr-applications", orgId, id, "extraction"] as const,
};

function ClaimItem({ claim }: { claim: HRClaim }) {
  const t = useTranslations("hrApplications.extraction");
  return (
    <li className="rounded-md border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{claim.title || "—"}</span>
        {claim.subtitle || claim.dates ? (
          <span className="text-muted-foreground">
            {[claim.subtitle, claim.dates].filter(Boolean).join(" · ")}
          </span>
        ) : null}
        <Badge variant="outline">{t(`confidence.${claim.confidence}`)}</Badge>
        {claim.inferred ? <Badge variant="outline">{t("inferred")}</Badge> : null}
      </div>
      {claim.detail ? <p className="text-muted-foreground mt-1">{claim.detail}</p> : null}
      {claim.snippet ? (
        <blockquote className="text-muted-foreground mt-1 border-l-2 pl-2 text-xs">
          {t("page", { page: claim.page ?? 1 })} “{claim.snippet}”
        </blockquote>
      ) : null}
      {claim.corrections.map((c) => (
        <p key={c.id} className="mt-2 rounded bg-amber-50 p-2 text-xs dark:bg-amber-950">
          <span className="font-medium">{t("correction")}</span>{" "}
          {c.remove
            ? t("correctionRemove")
            : Object.entries(c.values)
                .map(([k, v]) => `${k}: ${v}`)
                .join(" · ")}
          {c.note ? ` — “${c.note}”` : ""}
        </p>
      ))}
    </li>
  );
}

/** What was read from the candidate's CVs (evidence for reviewers) + "Retry processing". */
export function ExtractionPanel({ app }: { app: HRApplicationDetail }) {
  const t = useTranslations("hrApplications.extraction");
  const tf = useTranslations("hrApplications.extraction.flags");
  const tg = useTranslations("extraction.groups");
  const { orgId, role } = useJobsContext();
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const key = extractionKeys.panel(orgId ?? "", app.id);
  const panel = useQuery({
    queryKey: key,
    queryFn: () =>
      api.get<HRExtraction>(`/hr/applications/${app.id}/extraction/`, { orgId: orgId! }),
    enabled: !!orgId,
    refetchInterval: (q) => (q.state.data?.runs.some((r) => READING.has(r.status)) ? 3000 : false),
  });
  const retry = useMutation({
    mutationFn: () =>
      api.post<HRExtraction>(`/hr/applications/${app.id}/retry-processing/`, undefined, {
        orgId: orgId!,
      }),
    onSuccess: (data) => {
      setError(null);
      client.setQueryData(key, data);
      void client.invalidateQueries({
        queryKey: hrApplicationKeys.detail(orgId ?? "", app.id),
        exact: true, // the panel's own key shares this prefix; keep the retry result
      });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : t("retryFailed")),
  });

  return (
    <section aria-labelledby="hr-extraction" className="rounded-lg border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="hr-extraction" className="text-lg font-semibold">
          {t("title")}
        </h2>
        {panel.data?.can_retry && EDITORS.includes(role ?? "") ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => retry.mutate()}
            disabled={retry.isPending}
          >
            {retry.isPending ? t("retrying") : t("retry")}
          </Button>
        ) : null}
      </div>
      <p className="text-muted-foreground mt-1 text-xs">{t("aiLabel")}</p>
      {error ? (
        <Alert variant="destructive" role="alert" className="mt-2">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {panel.isPending ? (
        <PageSkeleton rows={2} />
      ) : panel.isError ? (
        <ErrorState error={panel.error} onRetry={() => panel.refetch()} />
      ) : panel.data.manual_review_requested ? (
        <p className="mt-2 text-sm">{t("manual")}</p>
      ) : panel.data.runs.length === 0 ? (
        <p className="text-muted-foreground mt-2 text-sm">{t("none")}</p>
      ) : (
        <div className="mt-3 flex flex-col gap-4">
          {(() => {
            const flags = FLAG_KEYS.filter(
              (f) =>
                panel.data.flags.includes(f) || panel.data.runs.some((r) => r.flags.includes(f)),
            );
            return flags.length ? (
              <Alert>
                <AlertTitle>{t("flagsTitle")}</AlertTitle>
                <AlertDescription>
                  <ul className="list-disc pl-5">
                    {flags.map((f) => (
                      <li key={f}>{tf(f)}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            ) : null;
          })()}
          {panel.data.runs.map((run) => {
            const { byType, summary } = grouped(run.claims);
            return (
              <div key={run.id} className="flex flex-col gap-3">
                <h3 className="text-sm font-semibold">
                  {run.filename}{" "}
                  <span className="text-muted-foreground font-normal">
                    {t("runMeta", { pages: run.page_count ?? 0, attempts: run.attempts })}
                  </span>
                </h3>
                {READING.has(run.status) ? (
                  <p role="status" aria-live="polite" className="text-muted-foreground text-sm">
                    {t("reading")}
                  </p>
                ) : run.status === "failed" ? (
                  <Alert variant="destructive">
                    <AlertTitle>{t("failedTitle")}</AlertTitle>
                    <AlertDescription>
                      {t("failedBody", { code: run.error_code || "unknown" })}
                    </AlertDescription>
                  </Alert>
                ) : (
                  <>
                    {summary?.detail ? <p className="text-sm">{summary.detail}</p> : null}
                    {GROUPS.map((g) =>
                      byType[g].length ? (
                        <section key={g} aria-label={tg(g)}>
                          <h4 className="mb-2 text-sm font-medium">{tg(g)}</h4>
                          <ul className="flex flex-col gap-2">
                            {byType[g].map((c) => (
                              <ClaimItem key={c.id} claim={c} />
                            ))}
                          </ul>
                        </section>
                      ) : null,
                    )}
                    {run.set_aside ? (
                      <p className="text-muted-foreground text-xs">
                        {t("setAside", { count: run.set_aside })}
                      </p>
                    ) : null}
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
