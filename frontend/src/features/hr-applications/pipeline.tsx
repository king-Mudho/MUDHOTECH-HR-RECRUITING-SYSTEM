"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type DragEvent } from "react";

import { ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Paginated } from "@/features/jobs/api";
import { useJob, useJobsContext } from "@/features/jobs/hooks";
import { api } from "@/lib/api-client";

import { APPLICATION_VIEWERS, PIPELINE_COLUMNS, type HRApplicationRow } from "./api";
import { MoveDialog } from "./move-dialog";

const DRAG_TYPE = "application/x-mhrs-application";

export function usePipeline(jobId: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: ["hr-applications", orgId ?? "", "job", jobId, "pipeline"],
    queryFn: () =>
      api.get<Paginated<HRApplicationRow>>(`/hr/jobs/${jobId}/applications/`, {
        orgId: orgId!,
        query: { page_size: 100 },
      }),
    enabled: !!orgId,
  });
}

/**
 * Pipeline board for one vacancy (FR-M13-02). Dropping a card on a column, or using the card's
 * "Move" button (keyboard), opens the move dialog; the server validates every change.
 */
export function PipelineBoard({ jobId }: { jobId: string }) {
  const t = useTranslations("hrApplications.pipeline");
  const { role, isPending, orgId } = useJobsContext();
  const job = useJob(jobId);
  const rows = usePipeline(jobId);
  const [moving, setMoving] = useState<{ id: string; to: string | null } | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [announce, setAnnounce] = useState("");

  if (isPending) return <PageSkeleton />;
  if (!orgId || !role || !APPLICATION_VIEWERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  if (rows.isPending) return <PageSkeleton />;
  if (rows.isError) return <ErrorState error={rows.error} onRetry={() => rows.refetch()} />;

  const byStatus = new Map<string, HRApplicationRow[]>();
  for (const r of rows.data.results) {
    byStatus.set(r.status, [...(byStatus.get(r.status) ?? []), r]);
  }
  const columns = PIPELINE_COLUMNS.filter(
    (c) => byStatus.has(c) || !["processing_error", "hired", "offer", "interview"].includes(c),
  );

  const onDrop = (e: DragEvent<HTMLElement>, status: string) => {
    e.preventDefault();
    setOver(null);
    const id = e.dataTransfer.getData(DRAG_TYPE);
    const row = rows.data.results.find((r) => r.id === id);
    if (row && row.status !== status) setMoving({ id, to: status });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Link
          href={`/hr/jobs/${jobId}/applications`}
          className="text-muted-foreground text-sm underline-offset-2 hover:underline"
        >
          {t("backToList")}
        </Link>
        <h1 className="text-2xl font-semibold">
          {t("title")}
          {job.data ? (
            <span className="text-muted-foreground font-normal"> · {job.data.title}</span>
          ) : null}
        </h1>
        <p className="text-muted-foreground text-sm">{t("help")}</p>
        {rows.data.count > rows.data.results.length ? (
          <p className="text-sm">
            {t("truncated", { shown: rows.data.results.length, total: rows.data.count })}
          </p>
        ) : null}
      </div>
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
      <div className="-mx-4 overflow-x-auto px-4 pb-2">
        <ol className="flex min-w-max gap-3" aria-label={t("boardLabel")}>
          {columns.map((status) => {
            const items = byStatus.get(status) ?? [];
            return (
              <li
                key={status}
                aria-labelledby={`col-${status}`}
                data-status={status}
                onDragOver={(e) => {
                  if (e.dataTransfer.types.includes(DRAG_TYPE)) {
                    e.preventDefault();
                    setOver(status);
                  }
                }}
                onDragLeave={() => setOver((o) => (o === status ? null : o))}
                onDrop={(e) => onDrop(e, status)}
                className={`bg-muted/40 flex w-64 shrink-0 flex-col gap-2 rounded-lg border p-2 ${
                  over === status ? "ring-primary ring-2" : ""
                }`}
              >
                <h2
                  id={`col-${status}`}
                  className="flex items-center justify-between px-1 text-sm font-semibold"
                >
                  <StatusBadge status={status} />
                  <span className="text-muted-foreground text-xs">
                    {t("count", { count: items.length })}
                  </span>
                </h2>
                {items.length === 0 ? (
                  <p className="text-muted-foreground px-1 py-4 text-center text-xs">
                    {t("emptyColumn")}
                  </p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {items.map((a) => (
                      <li
                        key={a.id}
                        draggable
                        onDragStart={(e) => {
                          e.dataTransfer.setData(DRAG_TYPE, a.id);
                          e.dataTransfer.effectAllowed = "move";
                        }}
                        className="bg-background flex cursor-grab flex-col gap-1.5 rounded-md border p-2 text-sm shadow-xs"
                      >
                        <Link
                          href={`/hr/applications/${a.id}`}
                          className="font-medium underline-offset-2 hover:underline"
                        >
                          {a.candidate_name || t("unnamed")}
                        </Link>
                        <span className="text-muted-foreground font-mono text-xs">
                          {a.reference}
                        </span>
                        {a.tags.length ? (
                          <span className="flex flex-wrap gap-1">
                            {a.tags.map((tag) => (
                              <Badge key={tag} variant="outline">
                                {tag}
                              </Badge>
                            ))}
                          </span>
                        ) : null}
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="min-h-8 self-start"
                          aria-label={t("moveLabel", { name: a.candidate_name || t("unnamed") })}
                          onClick={() => setMoving({ id: a.id, to: null })}
                        >
                          {t("move")}
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
      </div>
      {moving ? (
        <MoveDialog
          key={`${moving.id}:${moving.to ?? ""}`}
          applicationId={moving.id}
          target={moving.to}
          open
          onOpenChange={(o) => !o && setMoving(null)}
          onMoved={() => setAnnounce(t("moved"))}
        />
      ) : null}
    </div>
  );
}

export function PipelineRoute() {
  const { id } = useParams<{ id: string }>();
  return <PipelineBoard jobId={id} />;
}
