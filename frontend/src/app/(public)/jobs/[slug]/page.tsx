import { Building2, CalendarClock, FileText, MapPin } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ShareButtons, ViewerLocalTime } from "@/features/jobs/public/client";
import { Salary } from "@/features/jobs/public/components";
import { getPublicJob, jobPostingJsonLd, safeJsonLd } from "@/features/jobs/public-api";

const SITE = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export async function generateMetadata(props: PageProps<"/jobs/[slug]">): Promise<Metadata> {
  const { slug } = await props.params;
  const t = await getTranslations("publicJobs.detail");
  const found = await getPublicJob(slug);
  if (found.kind !== "ok") {
    return {
      title: found.kind === "gone" ? t("goneTitle") : t("notFoundTitle"),
      robots: { index: false },
    };
  }
  const job = found.job;
  const description = (job.summary || `${job.title} at ${job.organisation.name}`).slice(0, 160);
  const title = t("metaTitle", { title: job.title, company: job.organisation.name });
  return {
    title,
    description,
    alternates: { canonical: `/jobs/${job.slug}` },
    // Closed and unlisted vacancies stay reachable by link but are kept out of search engines.
    robots:
      job.is_closed || job.visibility === "unlisted" ? { index: false, follow: true } : undefined,
    openGraph: {
      title,
      description,
      url: `/jobs/${job.slug}`,
      type: "website",
      siteName: "MUDHOTECH HR RECRUITING SYSTEM",
      ...(job.organisation.logo_url ? { images: [{ url: job.organisation.logo_url }] } : {}),
    },
    twitter: { card: "summary", title, description },
  };
}

function Html({ html }: { html: string }) {
  // Server-sanitised with an allow-list on save (EC-JOB-12); rendered as stored.
  return (
    <div
      className="[&_a]:underline [&_h2]:mt-3 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:font-semibold [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:mt-2 [&_ul]:list-disc [&_ul]:pl-5"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

async function JobDetail({ params }: { params: PageProps<"/jobs/[slug]">["params"] }) {
  const { slug } = await params;
  const t = await getTranslations("publicJobs.detail");
  const tc = await getTranslations("jobs.choices");
  const format = await getFormatter();
  const found = await getPublicJob(slug);
  if (found.kind === "missing") notFound();
  if (found.kind === "gone" || found.kind === "unavailable") {
    return (
      <div className="flex flex-col gap-3 rounded-lg border p-8 text-center">
        <h1 className="text-2xl font-semibold">
          {found.kind === "gone" ? t("goneTitle") : t("unavailableTitle")}
        </h1>
        <p className="text-muted-foreground">
          {found.kind === "gone" ? t("gone") : t("unavailable")}
        </p>
        <Link href="/jobs" className="underline">
          {t("browse")}
        </Link>
      </div>
    );
  }
  const job = found.job;
  if (job.slug !== slug && slug !== job.id) permanentRedirect(`/jobs/${job.slug}`); // EC-JOB-13
  const url = `${SITE}/jobs/${job.slug}`;
  const where = job.locations.map((l) => l.city || l.name).join(", ");
  const deadline = job.closes_at
    ? format.dateTime(new Date(job.closes_at), {
        dateStyle: "full",
        timeStyle: "short",
        timeZone: job.timezone,
      })
    : null;
  return (
    <article className="flex flex-col gap-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: safeJsonLd(jobPostingJsonLd(job, SITE)) }}
      />
      {job.is_closed ? (
        <Alert role="status">
          <AlertTitle>{t("closedTitle")}</AlertTitle>
          <AlertDescription>
            {t("closed")}{" "}
            <Link href="/jobs" className="underline">
              {t("browse")}
            </Link>
          </AlertDescription>
        </Alert>
      ) : job.status === "paused" ? (
        <Alert role="status">
          <AlertDescription>{t("paused")}</AlertDescription>
        </Alert>
      ) : null}
      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-bold tracking-tight">{job.title}</h1>
        <p className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="inline-flex items-center gap-1">
            <Building2 aria-hidden="true" className="size-4" />
            <Link
              href={`/companies/${job.organisation.slug}`}
              className="underline-offset-2 hover:underline"
            >
              {job.organisation.name}
            </Link>
            {job.organisation.verified ? <Badge variant="secondary">{t("verified")}</Badge> : null}
          </span>
          {where ? (
            <span className="inline-flex items-center gap-1">
              <MapPin aria-hidden="true" className="size-4" />
              {where}
            </span>
          ) : null}
        </p>
        <ul className="flex flex-wrap gap-2 text-sm">
          <li>
            <Badge variant="outline">{tc(`employment.${job.employment_type}`)}</Badge>
          </li>
          <li>
            <Badge variant="outline">{tc(`workplace.${job.workplace_type}`)}</Badge>
          </li>
          {job.seniority ? (
            <li>
              <Badge variant="outline">{tc(`seniority.${job.seniority}`)}</Badge>
            </li>
          ) : null}
          {job.openings > 1 ? (
            <li>
              <Badge variant="outline">{t("openings", { count: job.openings })}</Badge>
            </li>
          ) : null}
        </ul>
        {job.salary ? (
          <p className="font-medium">
            <Salary salary={job.salary} />
          </p>
        ) : null}
        {deadline && job.closes_at ? (
          <div className="flex items-start gap-2">
            <CalendarClock aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
            <p>
              <span className="block font-medium">
                {t("closes", { date: deadline, zone: job.timezone })}
              </span>
              <ViewerLocalTime iso={job.closes_at} jobTimeZone={job.timezone} />
            </p>
          </div>
        ) : null}
        {job.accepts_applications ? (
          <div>
            <Button asChild size="lg" className="min-h-11 px-6">
              <Link href={`/apply/${job.id}`}>{t("apply")}</Link>
            </Button>
          </div>
        ) : null}
      </header>

      {job.summary ? <p className="text-lg">{job.summary}</p> : null}
      {job.responsibilities_html ? (
        <section aria-labelledby="responsibilities">
          <h2 id="responsibilities" className="text-xl font-semibold">
            {t("responsibilities")}
          </h2>
          <Html html={job.responsibilities_html} />
        </section>
      ) : null}
      <section aria-labelledby="requirements" className="flex flex-col gap-3">
        <h2 id="requirements" className="text-xl font-semibold">
          {t("requirements")}
        </h2>
        {job.requirements_html ? <Html html={job.requirements_html} /> : null}
        {job.essential_criteria.length > 0 ? (
          <div>
            <h3 className="font-semibold">{t("essential")}</h3>
            <ul className="mt-1 list-disc pl-5">
              {job.essential_criteria.map((c, i) => (
                <li key={`e-${i}`}>
                  {c.title}
                  {c.min_months
                    ? ` — ${t("minExperience", { years: Math.round((c.min_months / 12) * 10) / 10 })}`
                    : ""}
                  {(c.equivalents ?? []).length > 0 ? (
                    <span className="text-muted-foreground">
                      {" "}
                      ({t("equivalents", { list: c.equivalents.join(", ") })})
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {job.preferred_criteria.length > 0 ? (
          <div>
            <h3 className="font-semibold">{t("preferred")}</h3>
            <ul className="mt-1 list-disc pl-5">
              {job.preferred_criteria.map((c, i) => (
                <li key={`p-${i}`}>{c.title}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <p className="text-muted-foreground text-sm">{t("fairness")}</p>
      </section>
      {job.benefits_html ? (
        <section aria-labelledby="benefits">
          <h2 id="benefits" className="text-xl font-semibold">
            {t("benefits")}
          </h2>
          <Html html={job.benefits_html} />
        </section>
      ) : null}
      {job.required_documents.length > 0 ? (
        <section aria-labelledby="documents">
          <h2 id="documents" className="text-xl font-semibold">
            {t("documents")}
          </h2>
          <ul className="mt-2 flex flex-col gap-1">
            {job.required_documents.map((d) => (
              <li key={d} className="flex items-center gap-2">
                <FileText aria-hidden="true" className="size-4" />
                {tc.has(`documents.${d}`) ? tc(`documents.${d}`) : d}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section aria-labelledby="share" className="flex flex-col gap-2 border-t pt-4">
        <h2 id="share" className="font-semibold">
          {t("share")}
        </h2>
        <ShareButtons url={url} title={job.title} />
      </section>
    </article>
  );
}

/**
 * Rendered as one blocking response (no Suspense around the job; data is cached for 60 s). The
 * advert is the first paint on slow phones, and title/description/Open Graph land in <head> for
 * every user agent, so WhatsApp link previews and SEO audits see them (P03-T13).
 */
export const instant = false;

export default function JobPage(props: PageProps<"/jobs/[slug]">) {
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 py-8">
      <JobDetail params={props.params} />
    </main>
  );
}
