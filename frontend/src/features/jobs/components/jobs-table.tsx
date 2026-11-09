"use client";

import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";

import type { JobListParams } from "../api";
import { canJob, useJobs, useJobsContext } from "../hooks";

const FILTERS = [
  { key: "open", status: "draft,in_review,approved,scheduled,published,paused" },
  { key: "draft", status: "draft" },
  { key: "in_review", status: "in_review" },
  { key: "published", status: "published,scheduled" },
  { key: "paused", status: "paused" },
  { key: "closed", status: "closed" },
  { key: "archived", status: "archived" },
  { key: "all", status: "" },
] as const;

export function JobsTable() {
  const t = useTranslations("jobs.list");
  const format = useFormatter();
  const { role, isPending: ctxPending, orgId } = useJobsContext();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("open");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const id = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(id);
  }, [searchInput]);

  const params: JobListParams = {
    status: FILTERS.find((f) => f.key === filter)?.status || undefined,
    search: search || undefined,
    page,
  };
  const jobs = useJobs(params);

  if (ctxPending) return <PageSkeleton />;
  if (!orgId || !canJob(role, "jobs.view")) return <ForbiddenState description={t("forbidden")} />;

  const totalPages = jobs.data ? Math.max(1, Math.ceil(jobs.data.count / 25)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        {canJob(role, "jobs.create") ? (
          <Button asChild className="min-h-10">
            <Link href="/hr/jobs/new">
              <Plus aria-hidden="true" />
              {t("new")}
            </Link>
          </Button>
        ) : null}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex flex-col gap-1.5 sm:w-72">
          <Label htmlFor="job-search">{t("search")}</Label>
          <div className="relative">
            <Search
              aria-hidden="true"
              className="text-muted-foreground absolute top-3 left-2.5 size-4"
            />
            <Input
              id="job-search"
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder={t("searchPlaceholder")}
              className="h-10 pl-8"
            />
          </div>
        </div>
        <div role="group" aria-label={t("filterLabel")} className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => (
            <Button
              key={f.key}
              type="button"
              size="sm"
              variant={filter === f.key ? "default" : "outline"}
              aria-pressed={filter === f.key}
              className="min-h-9"
              onClick={() => {
                setFilter(f.key);
                setPage(1);
              }}
            >
              {t(`filters.${f.key}`)}
            </Button>
          ))}
        </div>
      </div>

      {jobs.isPending ? (
        <PageSkeleton />
      ) : jobs.isError ? (
        jobs.error instanceof ApiError && jobs.error.status === 403 ? (
          <ForbiddenState description={t("forbidden")} />
        ) : (
          <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />
        )
      ) : jobs.data.results.length === 0 ? (
        <EmptyState
          title={search || filter !== "open" ? t("noMatchesTitle") : t("emptyTitle")}
          description={search || filter !== "open" ? t("noMatches") : t("empty")}
          action={
            canJob(role, "jobs.create") && !search ? (
              <Button asChild>
                <Link href="/hr/jobs/new">{t("new")}</Link>
              </Button>
            ) : null
          }
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">{t("caption")}</caption>
              <thead className="bg-muted/50 text-left">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {t("columns.title")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {t("columns.status")}
                  </th>
                  <th scope="col" className="hidden px-3 py-2 font-medium md:table-cell">
                    {t("columns.version")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {t("columns.closes")}
                  </th>
                  <th scope="col" className="hidden px-3 py-2 font-medium lg:table-cell">
                    {t("columns.updated")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.data.results.map((job) => (
                  <tr key={job.id} className="border-t">
                    <td className="px-3 py-2">
                      <Link
                        href={`/hr/jobs/${job.id}`}
                        className="font-medium underline-offset-2 hover:underline"
                      >
                        {job.title}
                      </Link>
                      {job.reference_code ? (
                        <span className="text-muted-foreground ml-2 text-xs">
                          {job.reference_code}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="hidden px-3 py-2 md:table-cell">
                      {job.current_version ? `v${job.current_version.number}` : "—"}
                    </td>
                    <td className="px-3 py-2">
                      {job.closes_at
                        ? format.dateTime(new Date(job.closes_at), {
                            dateStyle: "medium",
                            timeZone: job.timezone,
                          })
                        : "—"}
                    </td>
                    <td className="hidden px-3 py-2 lg:table-cell">
                      {format.relativeTime(new Date(job.updated_at))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav
            aria-label={t("pagination")}
            className="flex items-center justify-between gap-2 text-sm"
          >
            <span aria-live="polite">
              {t("pageOf", { page, total: totalPages, count: jobs.data.count })}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                {t("previous")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!jobs.data.next}
                onClick={() => setPage((p) => p + 1)}
              >
                {t("next")}
              </Button>
            </div>
          </nav>
        </>
      )}
    </div>
  );
}
