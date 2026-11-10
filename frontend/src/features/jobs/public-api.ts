import { cacheLife, cacheTag } from "next/cache";

import type { components } from "@/types/api";

type S = components["schemas"];
export type PublicJob = S["PublicJobList"];
export type PublicJobDetail = S["PublicJobDetail"];
export type PublicCompany = S["PublicCompany"];
export type PublicJobPage = S["PaginatedPublicJobListList"];

/** Django origin as seen from the Next.js server (same variable the rewrites use). */
const API = `${process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000"}/api/v1`;

/** Public pages revalidate every 60 s (ISR-style, P03-T13). */
const PUBLIC_CACHE = { stale: 60, revalidate: 60, expire: 3600 } as const;

export type JobLookup =
  | { kind: "ok"; job: PublicJobDetail }
  | { kind: "gone" }
  | { kind: "missing" }
  | { kind: "unavailable" };

async function getJson(path: string): Promise<{ status: number; body: unknown }> {
  try {
    const res = await fetch(`${API}${path}`, {
      headers: { Accept: "application/json" },
      redirect: "follow",
    });
    const body: unknown = res.headers.get("content-type")?.includes("json")
      ? await res.json()
      : null;
    return { status: res.status, body };
  } catch {
    return { status: 0, body: null };
  }
}

export interface JobSearchParams {
  q?: string;
  location?: string;
  workplace_type?: string;
  employment_type?: string;
  org?: string;
  posted_within?: string;
  closing_within?: string;
  ordering?: string;
  page?: string;
}

export async function searchJobs(params: JobSearchParams): Promise<PublicJobPage | null> {
  "use cache";
  cacheLife(PUBLIC_CACHE);
  cacheTag("public-jobs");
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) qs.set(k, v);
  qs.set("page_size", "20");
  const { status, body } = await getJson(`/jobs/?${qs.toString()}`);
  return status === 200 ? (body as PublicJobPage) : null;
}

export async function getPublicJob(slug: string): Promise<JobLookup> {
  "use cache";
  cacheLife(PUBLIC_CACHE);
  cacheTag("public-jobs", `public-job:${slug}`);
  const { status, body } = await getJson(`/jobs/${encodeURIComponent(slug)}/`);
  if (status === 200) return { kind: "ok", job: body as PublicJobDetail };
  if (status === 410) return { kind: "gone" };
  if (status === 404) return { kind: "missing" };
  return { kind: "unavailable" };
}

export async function getCompany(slug: string): Promise<PublicCompany | null | "unavailable"> {
  "use cache";
  cacheLife(PUBLIC_CACHE);
  cacheTag("public-companies", `public-company:${slug}`);
  const { status, body } = await getJson(`/companies/${encodeURIComponent(slug)}/`);
  if (status === 200) return body as PublicCompany;
  if (status === 404) return null;
  return "unavailable";
}

const EMPLOYMENT_SCHEMA: Record<string, string> = {
  full_time: "FULL_TIME",
  part_time: "PART_TIME",
  contract: "CONTRACTOR",
  internship: "INTERN",
  attachment: "INTERN",
  temporary: "TEMPORARY",
  graduate_trainee: "FULL_TIME",
};

/** schema.org JobPosting for Google for Jobs (JSON-LD). */
export function jobPostingJsonLd(job: PublicJobDetail, siteUrl: string): Record<string, unknown> {
  const description = [
    job.summary,
    job.responsibilities_html,
    job.requirements_html,
    job.benefits_html,
  ]
    .filter(Boolean)
    .join("\n");
  const ld: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    title: job.title,
    description,
    identifier: { "@type": "PropertyValue", name: job.organisation.name, value: job.id },
    datePosted: job.published_at,
    validThrough: job.closes_at,
    employmentType: EMPLOYMENT_SCHEMA[job.employment_type] ?? "OTHER",
    hiringOrganization: {
      "@type": "Organization",
      name: job.organisation.name,
      sameAs: `${siteUrl}/companies/${job.organisation.slug}`,
      ...(job.organisation.logo_url ? { logo: job.organisation.logo_url } : {}),
    },
    directApply: true,
    url: `${siteUrl}/jobs/${job.slug}`,
  };
  if (job.workplace_type === "remote") {
    ld.jobLocationType = "TELECOMMUTE";
    ld.applicantLocationRequirements = { "@type": "Country", name: "Zimbabwe" };
  }
  if (job.locations.length > 0) {
    ld.jobLocation = job.locations.map((l) => ({
      "@type": "Place",
      address: {
        "@type": "PostalAddress",
        addressLocality: l.city || l.name,
        addressCountry: "ZW",
      },
    }));
  }
  if (job.salary) {
    ld.baseSalary = {
      "@type": "MonetaryAmount",
      currency: job.salary.currency,
      value: {
        "@type": "QuantitativeValue",
        ...(job.salary.min ? { minValue: Number(job.salary.min) } : {}),
        ...(job.salary.max ? { maxValue: Number(job.salary.max) } : {}),
        unitText: job.salary.period.toUpperCase(),
      },
    };
  }
  return ld;
}

/** Serialise JSON-LD safely inside a <script> tag (no `</script>` break-out). */
export function safeJsonLd(data: unknown): string {
  return JSON.stringify(data)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026");
}
