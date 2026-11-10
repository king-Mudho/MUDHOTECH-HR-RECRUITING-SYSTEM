import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { JobCard } from "@/features/jobs/public/components";
import { getCompany } from "@/features/jobs/public-api";

export async function generateMetadata(props: PageProps<"/companies/[slug]">): Promise<Metadata> {
  const { slug } = await props.params;
  const t = await getTranslations("publicJobs.company");
  const company = await getCompany(slug);
  if (!company || company === "unavailable")
    return { title: t("notFoundTitle"), robots: { index: false } };
  const description = t("metaDescription", { name: company.name, count: company.open_jobs.length });
  return {
    title: t("metaTitle", { name: company.name }),
    description,
    alternates: { canonical: `/companies/${company.slug}` },
    openGraph: {
      title: company.name,
      description,
      url: `/companies/${company.slug}`,
      type: "website",
      ...(company.logo_url ? { images: [{ url: company.logo_url }] } : {}),
    },
  };
}

async function Company({ params }: { params: PageProps<"/companies/[slug]">["params"] }) {
  const { slug } = await params;
  const t = await getTranslations("publicJobs.company");
  const company = await getCompany(slug);
  if (company === null) notFound();
  if (company === "unavailable") {
    return (
      <p role="alert" className="rounded-lg border p-6 text-center">
        {t("unavailable")}
      </p>
    );
  }
  const place = [company.city, company.country].filter(Boolean).join(", ");
  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-center gap-4">
        {company.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- presigned storage URL, sized by CSS
          <img
            src={company.logo_url}
            alt=""
            width={64}
            height={64}
            className="size-16 rounded-md border object-contain"
          />
        ) : null}
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{company.name}</h1>
          <p className="text-muted-foreground">
            {[company.industry, place].filter(Boolean).join(" · ")}
          </p>
          {company.website ? (
            <a
              href={company.website}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="text-sm underline"
            >
              {t("website")}
            </a>
          ) : null}
        </div>
      </header>
      {company.description ? (
        // Sanitised server-side (nh3 allow-list) when the organisation profile is saved.
        <div
          className="[&_a]:underline [&_ul]:list-disc [&_ul]:pl-5"
          dangerouslySetInnerHTML={{ __html: company.description }}
        />
      ) : null}
      <section aria-labelledby="open-jobs" className="flex flex-col gap-3">
        <h2 id="open-jobs" className="text-xl font-semibold">
          {t("openJobs", { count: company.open_jobs.length })}
        </h2>
        {company.open_jobs.length === 0 ? (
          <p className="text-muted-foreground">
            {t("noJobs")}{" "}
            <Link href="/jobs" className="underline">
              {t("browse")}
            </Link>
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {company.open_jobs.map((job) => (
              <li key={job.id}>
                <JobCard job={job} headingLevel={3} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/** One blocking response, like the job page (metadata already waits on the cached data). */
export const instant = false;

export default function CompanyPage(props: PageProps<"/companies/[slug]">) {
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-4xl flex-1 flex-col px-4 py-8">
      <Company params={props.params} />
    </main>
  );
}
