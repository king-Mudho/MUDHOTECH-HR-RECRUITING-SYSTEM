"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

import type { ReportFilters } from "./components";

type ExportJob = components["schemas"]["ExportJob"];
type Download = components["schemas"]["ExportDownload"];

export function exportBody(
  kind: "report" | "applicants",
  format: string,
  blind: boolean,
  f: ReportFilters,
) {
  return {
    kind,
    format,
    blind: kind === "applicants" ? blind : false,
    job: f.job || null,
    department: f.department || null,
    date_from: f.from || null,
    date_to: f.to || null,
  };
}

/** Request an export of what is on screen; the file is built in the background (15-min links). */
export function ExportPanel({ filters }: { filters: ReportFilters }) {
  const t = useTranslations("reports.export");
  const format = useFormatter();
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const [kind, setKind] = useState<"report" | "applicants">("report");
  const [fmt, setFmt] = useState("xlsx");
  const [blind, setBlind] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const ids = { kind: useId(), fmt: useId(), blind: useId() };
  const listKey = ["exports", orgId ?? ""] as const;
  const list = useQuery({
    queryKey: listKey,
    queryFn: () => api.get<ExportJob[]>("/hr/exports/", { orgId: orgId! }),
    enabled: !!orgId,
    // poll while something is being built
    refetchInterval: (q) =>
      (q.state.data ?? []).some((e) => e.status === "queued") ? 3000 : false,
  });
  const create = useMutation({
    mutationFn: () =>
      api.post<ExportJob>("/hr/exports/", exportBody(kind, fmt, blind, filters), {
        orgId: orgId!,
      }),
    onSuccess: async () => {
      setError(null);
      await client.invalidateQueries({ queryKey: listKey });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : t("failed")),
  });
  const download = useMutation({
    mutationFn: (id: string) =>
      api.post<Download>(`/hr/exports/${id}/download/`, {}, { orgId: orgId! }),
    onSuccess: (d) => {
      window.location.assign(d.url);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : t("failed")),
  });
  const needsJob = kind === "applicants" && !filters.job;
  const select = "border-input bg-background h-10 rounded-md border px-2 text-sm";
  return (
    <section aria-labelledby="exports" className="flex flex-col gap-3 rounded-lg border p-4">
      <h2 id="exports" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-xs">{t("intro")}</p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={ids.kind}>{t("what")}</Label>
          <select
            id={ids.kind}
            className={select}
            value={kind}
            onChange={(e) => setKind(e.target.value as "report" | "applicants")}
          >
            <option value="report">{t("kinds.report")}</option>
            <option value="applicants">{t("kinds.applicants")}</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={ids.fmt}>{t("format")}</Label>
          <select
            id={ids.fmt}
            className={select}
            value={fmt}
            onChange={(e) => setFmt(e.target.value)}
          >
            <option value="xlsx">Excel (XLSX)</option>
            <option value="csv">CSV</option>
            <option value="pdf">PDF</option>
          </select>
        </div>
        {kind === "applicants" ? (
          <label htmlFor={ids.blind} className="flex h-10 items-center gap-2 text-sm">
            <input
              id={ids.blind}
              type="checkbox"
              className="size-5"
              checked={blind}
              onChange={(e) => setBlind(e.target.checked)}
            />
            {t("blind")}
          </label>
        ) : null}
        <Button
          className="h-10"
          disabled={needsJob || create.isPending}
          onClick={() => create.mutate()}
        >
          {t("request")}
        </Button>
      </div>
      {needsJob ? <p className="text-muted-foreground text-xs">{t("needsJob")}</p> : null}
      <p aria-live="polite" className="text-destructive text-sm">
        {error}
      </p>
      {list.data && list.data.length ? (
        <ul className="flex flex-col gap-2 text-sm">
          {list.data.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-2 rounded-md border p-2">
              <span className="font-medium">
                {t(`kinds.${e.kind === "applicants" ? "applicants" : "report"}`)} ·{" "}
                {e.format.toUpperCase()}
                {e.blind ? ` · ${t("blindShort")}` : ""}
              </span>
              <span className="text-muted-foreground">
                {format.dateTime(new Date(e.created_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
              </span>
              <span className="text-muted-foreground">
                {t(`status.${e.status}`)}
                {e.status === "failed" && e.error ? `: ${e.error}` : ""}
              </span>
              {e.status === "ready" ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto"
                  disabled={download.isPending}
                  onClick={() => download.mutate(e.id)}
                >
                  {t("download", { rows: e.row_count })}
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
