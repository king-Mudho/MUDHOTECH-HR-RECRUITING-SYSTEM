"use client";

import { CheckCircle2, CircleAlert, TriangleAlert } from "lucide-react";
import { useTranslations } from "next-intl";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import type { Readiness } from "../api";
import { useReadiness } from "../hooks";

/** Publish-readiness checklist (SRS §3.2, EC-JOB-01). Every failing check is listed. */
export function ReadinessPanel({
  jobId,
  stage,
  compact = false,
  data,
}: {
  jobId: string;
  stage: "submit" | "publish";
  compact?: boolean;
  /** Supply a result directly (e.g. from a 422 response) instead of fetching. */
  data?: Readiness;
}) {
  const t = useTranslations("jobs.readiness");
  const query = useReadiness(jobId, stage, !data);
  const result = data ?? query.data;
  return (
    <section aria-labelledby={`readiness-${stage}`} className="rounded-lg border p-4">
      <h2 id={`readiness-${stage}`} className="font-semibold">
        {t(stage === "submit" ? "titleSubmit" : "titlePublish")}
      </h2>
      {!result ? (
        query.isError ? (
          <p className="text-muted-foreground mt-2 text-sm">{t("unavailable")}</p>
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-5 w-full" />
            ))}
          </div>
        )
      ) : (
        <>
          <p className="mt-1 text-sm" aria-live="polite">
            {result.ready
              ? t("ready")
              : t("notReady", { count: result.checks.filter((c) => !c.ok && c.blocking).length })}
          </p>
          <ul className="mt-3 flex flex-col gap-2 text-sm">
            {result.checks.map((c) => (
              <li
                key={c.id}
                className={cn("flex gap-2", compact && c.ok && "text-muted-foreground")}
              >
                {c.ok ? (
                  <CheckCircle2
                    aria-hidden="true"
                    className="text-success mt-0.5 size-4 shrink-0"
                  />
                ) : (
                  <CircleAlert
                    aria-hidden="true"
                    className="text-destructive mt-0.5 size-4 shrink-0"
                  />
                )}
                <span>
                  <span className="sr-only">{c.ok ? t("passed") : t("failed")}: </span>
                  {t.has(`checks.${c.id}`) ? t(`checks.${c.id}`) : c.message}
                </span>
              </li>
            ))}
          </ul>
          {result.warnings.length > 0 ? (
            <>
              <h3 className="mt-4 text-sm font-semibold">{t("warnings")}</h3>
              <ul className="mt-2 flex flex-col gap-2 text-sm">
                {result.warnings.map((w, i) => {
                  const id = String(w.id ?? "");
                  return (
                    <li key={`${id}-${i}`} className="flex gap-2">
                      <TriangleAlert
                        aria-hidden="true"
                        className="text-warning mt-0.5 size-4 shrink-0"
                      />
                      <span>
                        {id === "protected_topic"
                          ? t("protectedTopic", {
                              question: String(w.question ?? ""),
                              justified: w.justified ? "yes" : "no",
                            })
                          : t.has(`warningsText.${id}`)
                            ? t(`warningsText.${id}`)
                            : String(w.message ?? id)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </>
          ) : null}
        </>
      )}
    </section>
  );
}
