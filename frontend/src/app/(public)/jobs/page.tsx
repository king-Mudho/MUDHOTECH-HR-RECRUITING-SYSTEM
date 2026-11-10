import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { JobCard, JobSearchForm } from "@/features/jobs/public/components";
import { searchJobs, type JobSearchParams } from "@/features/jobs/public-api";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("publicJobs.list");
  return {
    title: t("title"),
    description: t("description"),
    alternates: { canonical: "/jobs", types: { "application/rss+xml": "/jobs/feed.rss" } },
    openGraph: { title: t("title"), description: t("description"), url: "/jobs", type: "website" },
  };
}

const KEYS: (keyof JobSearchParams)[] = [
  "q",
  "location",
  "workplace_type",
  "employment_type",
  "org",
  "posted_within",
  "closing_within",
  "ordering",
  "page",
];

function pick(raw: Record<string, string | string[] | undefined>): JobSearchParams {
  const out: JobSearchParams = {};
  for (const k of KEYS) {
    const v = raw[k];
    const s = (Array.isArray(v) ? v[0] : v)?.trim().slice(0, 200);
    if (s) out[k] = s;
  }
  return out;
}

function hrefFor(params: JobSearchParams, page: number): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v && k !== "page") qs.set(k, v);
  if (page > 1) qs.set("page", String(page));
  const s = qs.toString();
  return s ? `/jobs?${s}` : "/jobs";
}

async function Results({ searchParams }: { searchParams: PageProps<"/jobs">["searchParams"] }) {
  const t = await getTranslations("publicJobs.list");
  const params = pick(await searchParams);
  const data = await searchJobs(params);
  const page = Math.max(1, Number(params.page ?? 1) || 1);
  return (
    <>
      <JobSearchForm params={params} />
      {data === null ? (
        <p role="alert" className="rounded-lg border p-6 text-center">
          {t("unavailable")}
        </p>
      ) : (
        <section aria-labelledby="results-title" className="flex flex-col gap-3">
          <h2 id="results-title" className="text-lg font-semibold" aria-live="polite">
            {t("count", { count: data.count })}
          </h2>
          {data.results.length === 0 ? (
            <div className="rounded-lg border border-dashed p-8 text-center">
              <p className="font-medium">{t("emptyTitle")}</p>
              <p className="text-muted-foreground mt-1 text-sm">{t("empty")}</p>
              <Link href="/jobs" className="mt-3 inline-block underline">
                {t("clear")}
              </Link>
            </div>
          ) : (
            <ul className="flex flex-col gap-3">
              {data.results.map((job) => (
                <li key={job.id}>
                  <JobCard job={job} />
                </li>
              ))}
            </ul>
          )}
          {data.previous || data.next ? (
            <nav aria-label={t("pagination")} className="flex justify-between gap-2 text-sm">
              {data.previous ? (
                <Link href={hrefFor(params, page - 1)} rel="prev" className="underline">
                  {t("previous")}
                </Link>
              ) : (
                <span />
              )}
              {data.next ? (
                <Link href={hrefFor(params, page + 1)} rel="next" className="underline">
                  {t("next")}
                </Link>
              ) : null}
            </nav>
          ) : null}
        </section>
      )}
    </>
  );
}

/**
 * One blocking response (no Suspense around the results; search data is cached for 60 s) so the
 * vacancy list is in the visible HTML for no-JS and old browsers (EC-APP-21) and for crawlers.
 */
export const instant = false;

export default async function JobsPage(props: PageProps<"/jobs">) {
  const t = await getTranslations("publicJobs.list");
  return (
    <main
      id="main-content"
      className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-8"
    >
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground mt-2">{t("description")}</p>
      </div>
      <Results searchParams={props.searchParams} />
    </main>
  );
}
