import { Building2, MapPin, Search } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { JobSearchParams, PublicJob } from "../public-api";
import { EMPLOYMENT_TYPES, WORKPLACE_TYPES } from "../schemas";

export function Salary({ salary }: { salary: PublicJob["salary"] }) {
  const t = useTranslations("publicJobs");
  const format = useFormatter();
  if (!salary) return null;
  const fmt = (v: string | null) =>
    v ? format.number(Number(v), { maximumFractionDigits: 0 }) : null;
  const min = fmt(salary.min);
  const max = fmt(salary.max);
  const range = min && max ? `${min}–${max}` : (min ?? max);
  // EC-JOB-15: shown in the advertised currency only; never converted.
  return (
    <span>
      {t("salary", { currency: salary.currency, range: range ?? "", period: salary.period })}
    </span>
  );
}

export function JobCard({ job, headingLevel = 2 }: { job: PublicJob; headingLevel?: 2 | 3 }) {
  const t = useTranslations("publicJobs");
  const tc = useTranslations("jobs.choices");
  const format = useFormatter();
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const where = job.locations.map((l) => l.city || l.name).join(", ");
  return (
    <article className="hover:border-primary/40 rounded-lg border p-4 transition-colors">
      <Heading className="text-lg font-semibold">
        <Link href={`/jobs/${job.slug}`} className="underline-offset-2 hover:underline">
          {job.title}
        </Link>
      </Heading>
      <p className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="inline-flex items-center gap-1">
          <Building2 aria-hidden="true" className="size-4" />
          {job.organisation.name}
          {job.organisation.verified ? (
            <Badge variant="secondary" className="ml-1">
              {t("verified")}
            </Badge>
          ) : null}
        </span>
        {where ? (
          <span className="inline-flex items-center gap-1">
            <MapPin aria-hidden="true" className="size-4" />
            {where}
          </span>
        ) : null}
      </p>
      {job.summary ? <p className="mt-2 line-clamp-2 text-sm">{job.summary}</p> : null}
      <p className="text-muted-foreground mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
        <span>{tc(`employment.${job.employment_type}`)}</span>
        <span>{tc(`workplace.${job.workplace_type}`)}</span>
        <Salary salary={job.salary} />
        {job.closes_at ? (
          <span>
            {t("closesOn", {
              date: format.dateTime(new Date(job.closes_at), {
                dateStyle: "medium",
                timeZone: job.timezone,
              }),
            })}
          </span>
        ) : null}
      </p>
    </article>
  );
}

/** Plain GET form: works without JavaScript and keeps filters in the URL (shareable, SSR). */
export function JobSearchForm({
  params = {},
  compact = false,
}: {
  params?: JobSearchParams;
  compact?: boolean;
}) {
  const t = useTranslations("publicJobs.search");
  const tc = useTranslations("jobs.choices");
  return (
    <form action="/jobs" method="get" role="search" className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="flex flex-1 flex-col gap-1.5">
          <Label htmlFor="job-q" className={compact ? "sr-only" : undefined}>
            {t("keywords")}
          </Label>
          <Input
            id="job-q"
            name="q"
            type="search"
            defaultValue={params.q ?? ""}
            placeholder={t("keywordsPlaceholder")}
            className="h-11"
          />
        </div>
        <div className="flex flex-col gap-1.5 sm:w-56">
          <Label htmlFor="job-location" className={compact ? "sr-only" : undefined}>
            {t("location")}
          </Label>
          <Input
            id="job-location"
            name="location"
            defaultValue={params.location ?? ""}
            placeholder={t("locationPlaceholder")}
            className="h-11"
          />
        </div>
        <Button type="submit" className="h-11 self-end px-5">
          <Search aria-hidden="true" />
          {t("submit")}
        </Button>
      </div>
      {compact ? null : (
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="job-employment">{t("employment")}</Label>
            <select
              id="job-employment"
              name="employment_type"
              defaultValue={params.employment_type ?? ""}
              className="border-input bg-background h-10 rounded-md border px-2 text-sm"
            >
              <option value="">{t("any")}</option>
              {EMPLOYMENT_TYPES.map((v) => (
                <option key={v} value={v}>
                  {tc(`employment.${v}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="job-workplace">{t("workplace")}</Label>
            <select
              id="job-workplace"
              name="workplace_type"
              defaultValue={params.workplace_type ?? ""}
              className="border-input bg-background h-10 rounded-md border px-2 text-sm"
            >
              <option value="">{t("any")}</option>
              {WORKPLACE_TYPES.map((v) => (
                <option key={v} value={v}>
                  {tc(`workplace.${v}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="job-ordering">{t("ordering")}</Label>
            <select
              id="job-ordering"
              name="ordering"
              defaultValue={params.ordering ?? ""}
              className="border-input bg-background h-10 rounded-md border px-2 text-sm"
            >
              <option value="">{t("orderDefault")}</option>
              <option value="newest">{t("orderNewest")}</option>
              <option value="closing">{t("orderClosing")}</option>
            </select>
          </div>
        </div>
      )}
    </form>
  );
}
