"use client";

import { Download, Search } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScanChip } from "@/features/candidates/components/documents";
import { documentsApi } from "@/features/documents/api";
import { useJob, useJobsContext } from "@/features/jobs/hooks";
import { ApiError } from "@/lib/api-client";

import { APPLICATION_VIEWERS, useHRApplication, useJobApplications } from "./api";

const FILTERS = [
  { key: "active", status: "submitted,processing,processing_error,under_review,on_hold" },
  { key: "withdrawn", status: "withdrawn" },
  { key: "all", status: "" },
] as const;

function Denied({ error }: { error: unknown }) {
  const t = useTranslations("hrApplications");
  if (error instanceof ApiError && error.status === 404)
    return <ForbiddenState title={t("notFoundTitle")} description={t("notFound")} />;
  if (error instanceof ApiError && error.status === 403)
    return <ForbiddenState description={t("forbidden")} />;
  return <ErrorState error={error} />;
}

export function JobApplicationsList({ jobId }: { jobId: string }) {
  const t = useTranslations("hrApplications");
  const format = useFormatter();
  const { role, isPending, orgId } = useJobsContext();
  const job = useJob(jobId);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("active");
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
  const apps = useJobApplications(jobId, {
    status: FILTERS.find((f) => f.key === filter)?.status || undefined,
    search: search || undefined,
    page,
  });

  if (isPending) return <PageSkeleton />;
  if (!orgId || !role || !APPLICATION_VIEWERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  const totalPages = apps.data ? Math.max(1, Math.ceil(apps.data.count / 25)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Link
          href={`/hr/jobs/${jobId}`}
          className="text-muted-foreground text-sm underline-offset-2 hover:underline"
        >
          {t("backToJob")}
        </Link>
        <h1 className="text-2xl font-semibold">
          {t("title")}
          {job.data ? (
            <span className="text-muted-foreground font-normal"> · {job.data.title}</span>
          ) : null}
        </h1>
        <p className="text-muted-foreground text-sm">{t("phaseNote")}</p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex flex-col gap-1.5 sm:w-72">
          <Label htmlFor="application-search">{t("search")}</Label>
          <div className="relative">
            <Search
              aria-hidden="true"
              className="text-muted-foreground absolute top-3 left-2.5 size-4"
            />
            <Input
              id="application-search"
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

      {apps.isPending ? (
        <PageSkeleton />
      ) : apps.isError ? (
        <Denied error={apps.error} />
      ) : apps.data.results.length === 0 ? (
        <EmptyState
          title={search || filter !== "active" ? t("noMatchesTitle") : t("emptyTitle")}
          description={search || filter !== "active" ? t("noMatches") : t("empty")}
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <caption className="sr-only">{t("caption")}</caption>
              <thead className="bg-muted/50 text-left">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {t("columns.candidate")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {t("columns.status")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {t("columns.submitted")}
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {t("columns.reference")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {apps.data.results.map((a) => (
                  <tr key={a.id} className="border-t">
                    <td className="px-3 py-2">
                      <Link
                        href={`/hr/applications/${a.id}`}
                        className="font-medium underline-offset-2 hover:underline"
                      >
                        {a.candidate_name || t("unnamed")}
                      </Link>
                      <div className="flex flex-wrap gap-1 pt-1">
                        {a.is_assisted ? <Badge variant="outline">{t("assisted")}</Badge> : null}
                        {a.objects_to_automated_processing ? (
                          <Badge variant="outline">{t("humanOnly")}</Badge>
                        ) : null}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={a.status} />
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {a.submitted_at
                        ? format.dateTime(new Date(a.submitted_at), {
                            dateStyle: "medium",
                            timeStyle: "short",
                          })
                        : "—"}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{a.reference}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav
            aria-label={t("pagination")}
            className="flex items-center justify-between gap-2 text-sm"
          >
            <span aria-live="polite">{t("count", { count: apps.data.count })}</span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                {t("previous")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
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

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function HRApplicationView({ id }: { id: string }) {
  const t = useTranslations("hrApplications");
  const format = useFormatter();
  const { role, isPending, orgId } = useJobsContext();
  const app = useHRApplication(id);
  if (isPending || (orgId && app.isPending)) return <PageSkeleton />;
  if (!orgId || !role || !APPLICATION_VIEWERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  if (app.isError) return <Denied error={app.error} />;
  const a = app.data!;
  const c = a.candidate as Record<string, unknown>;
  const when = (iso: string | null | undefined) =>
    iso ? format.dateTime(new Date(iso), { dateStyle: "medium", timeStyle: "short" }) : "—";
  const contactRows: [string, unknown][] = [
    [t("detail.email"), c.email],
    [t("detail.phone"), c.phone],
    [t("detail.city"), [c.city, c.country].filter(Boolean).join(", ")],
    [t("detail.headline"), c.headline],
    [t("detail.availability"), c.availability],
  ];
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <Link
          href={`/hr/jobs/${a.job.id}/applications`}
          className="text-muted-foreground text-sm underline-offset-2 hover:underline"
        >
          {t("backToList", { job: a.job.title })}
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{a.candidate_name || t("unnamed")}</h1>
          <StatusBadge status={a.status} />
        </div>
        <p className="text-muted-foreground text-sm">
          {t("detail.meta", {
            reference: a.reference ?? "",
            when: when(a.submitted_at),
            version: a.job.version,
          })}
        </p>
        <div className="flex flex-wrap gap-1">
          {a.is_assisted ? <Badge variant="outline">{t("assisted")}</Badge> : null}
          {a.objects_to_automated_processing ? (
            <Badge variant="outline">{t("humanOnlyLong")}</Badge>
          ) : null}
        </div>
      </div>

      <section aria-labelledby="hr-contact" className="rounded-lg border p-4">
        <h2 id="hr-contact" className="text-lg font-semibold">
          {t("detail.contact")}
        </h2>
        <dl className="mt-2 grid gap-1 text-sm sm:grid-cols-[10rem_1fr]">
          {contactRows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted-foreground">{label}</dt>
              <dd>{formatValue(value)}</dd>
            </div>
          ))}
        </dl>
        {typeof c.summary === "string" && c.summary ? (
          <p className="mt-3 text-sm whitespace-pre-line">{c.summary}</p>
        ) : null}
      </section>

      <section aria-labelledby="hr-docs" className="rounded-lg border p-4">
        <h2 id="hr-docs" className="text-lg font-semibold">
          {t("detail.documents")}
        </h2>
        {a.documents.length === 0 ? (
          <p className="text-muted-foreground mt-2 text-sm">{t("detail.noDocuments")}</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-2">
            {a.documents.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium">{d.filename}</span>
                  <span className="text-muted-foreground">({d.required_doc_key || d.role})</span>
                  <ScanChip status={d.scan_status} />
                </span>
                {d.available ? (
                  <Button asChild size="sm" variant="outline">
                    <a href={documentsApi.downloadUrl(d.id)}>
                      <Download aria-hidden="true" />
                      {t("detail.download", { name: d.filename })}
                    </a>
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="hr-answers" className="rounded-lg border p-4">
        <h2 id="hr-answers" className="text-lg font-semibold">
          {t("detail.answers")}
        </h2>
        {a.answers.length === 0 ? (
          <p className="text-muted-foreground mt-2 text-sm">{t("detail.noAnswers")}</p>
        ) : (
          <dl className="mt-2 flex flex-col gap-3 text-sm">
            {a.answers.map((q) => (
              <div key={q.key}>
                <dt className="font-medium">{q.prompt}</dt>
                <dd className="whitespace-pre-line">
                  {q.document_id ? (
                    <a href={documentsApi.downloadUrl(q.document_id)} className="underline">
                      {t("detail.attachedFile")}
                    </a>
                  ) : (
                    formatValue(q.value)
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section aria-labelledby="hr-timeline" className="rounded-lg border p-4">
        <h2 id="hr-timeline" className="text-lg font-semibold">
          {t("detail.timeline")}
        </h2>
        <ol className="mt-2 flex flex-col gap-2 text-sm">
          {a.timeline.map((e, i) => (
            <li key={`${e.at}-${i}`} className="flex flex-wrap items-center gap-2">
              <StatusBadge status={e.to_status} />
              <span className="text-muted-foreground">
                {when(e.at)} · {t(`detail.actor.${e.actor_type === "human" ? "human" : "system"}`)}
              </span>
              {e.reason_text ? <span>— {e.reason_text}</span> : null}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

export function JobApplicationsRoute() {
  const { id } = useParams<{ id: string }>();
  return <JobApplicationsList jobId={id} />;
}

export function HRApplicationRoute() {
  const { id } = useParams<{ id: string }>();
  return <HRApplicationView id={id} />;
}
