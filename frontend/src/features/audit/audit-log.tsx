"use client";

import { useInfiniteQuery, type InfiniteData } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useMemo, useState } from "react";

import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useJobsContext } from "@/features/jobs/hooks";
import { api } from "@/lib/api-client";
import { downloadWithOrg } from "@/lib/download";
import type { components } from "@/types/api";

type AuditEvent = components["schemas"]["AuditEvent"];
interface Page {
  next_cursor: string | null;
  results: AuditEvent[];
}
interface Filters {
  action?: string;
  target_id?: string;
  from?: string;
  to?: string;
}

/** Mirrors backend `audit.view` (UI hiding only). */
export const AUDIT_VIEWERS = ["org_admin", "auditor"];

function clean(f: Filters) {
  return Object.fromEntries(Object.entries(f).filter(([, v]) => v)) as Record<string, string>;
}

export function AuditLog() {
  const t = useTranslations("audit");
  const format = useFormatter();
  const { orgId, role, isPending } = useJobsContext();
  const [filters, setFilters] = useState<Filters>({});
  const [draft, setDraft] = useState<Filters>({});
  const id = useId();
  const query = useInfiniteQuery({
    queryKey: ["audit-events", orgId ?? "", clean(filters)],
    queryFn: ({ pageParam }) =>
      api.get<Page>("/hr/audit-events/", {
        orgId: orgId!,
        query: { ...clean(filters), ...(pageParam ? { cursor: pageParam } : {}) },
      }),
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !!orgId && AUDIT_VIEWERS.includes(role ?? ""),
  });
  const rows = useMemo(
    () => (query.data as InfiniteData<Page> | undefined)?.pages.flatMap((p) => p.results) ?? [],
    [query.data],
  );
  if (isPending) return <PageSkeleton />;
  if (!orgId || !AUDIT_VIEWERS.includes(role ?? ""))
    return <ForbiddenState description={t("forbidden")} />;
  const exportUrl = `/api/v1/hr/audit-events/export/?${new URLSearchParams(clean(filters))}`;
  const field = (key: keyof Filters, label: string, type = "text") => (
    <div className="flex flex-col gap-1">
      <Label htmlFor={`${id}-${key}`}>{label}</Label>
      <Input
        id={`${id}-${key}`}
        type={type}
        className="h-9"
        value={draft[key] ?? ""}
        onChange={(e) => setDraft({ ...draft, [key]: e.target.value || undefined })}
      />
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-xl font-semibold">{t("title")}</h2>
        <p className="text-muted-foreground text-sm">{t("intro")}</p>
      </div>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setFilters(draft);
        }}
      >
        {field("action", t("action"))}
        {field("target_id", t("target"))}
        {field("from", t("from"), "date")}
        {field("to", t("to"), "date")}
        <Button type="submit" size="sm">
          {t("apply")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void downloadWithOrg(exportUrl, orgId, "audit-events.csv")}
        >
          {t("export")}
        </Button>
      </form>
      {query.isPending ? (
        <PageSkeleton />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title={t("emptyTitle")} description={t("empty")} />
      ) : (
        <div
          className="overflow-x-auto rounded-lg border"
          tabIndex={0}
          role="region"
          aria-label={t("caption")}
        >
          <table className="w-full text-sm">
            <caption className="sr-only">{t("caption")}</caption>
            <thead className="bg-muted/50 text-left">
              <tr>
                {(["when", "who", "action", "target", "reason"] as const).map((c) => (
                  <th key={c} scope="col" className="px-3 py-2 font-medium">
                    {t(`columns.${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} className="border-t align-top">
                  <td className="px-3 py-2 whitespace-nowrap">
                    {format.dateTime(new Date(e.created_at), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </td>
                  <td className="px-3 py-2">{e.actor ?? t(`actorType.${e.actor_type}`)}</td>
                  <td className="px-3 py-2 font-mono text-xs">{e.action}</td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {e.target_type}
                    {e.target_id ? ` ${e.target_id.slice(0, 8)}` : ""}
                  </td>
                  <td className="px-3 py-2">{e.reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {query.hasNextPage ? (
        <Button
          variant="outline"
          size="sm"
          className="self-start"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          {t("more")}
        </Button>
      ) : null}
    </div>
  );
}
