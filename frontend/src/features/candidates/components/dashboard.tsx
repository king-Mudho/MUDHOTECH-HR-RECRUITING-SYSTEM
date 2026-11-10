"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

import { candidateApi } from "../api";
import { useApplications, useProfile } from "../hooks";
import { shownStatus } from "./applications";

type PublicJobs = components["schemas"]["PaginatedPublicJobListList"];

export function CandidateDashboard() {
  const t = useTranslations("candidate.dashboard");
  const ts = useTranslations("status");
  const apps = useApplications();
  const profile = useProfile();
  const skills = useQuery({
    queryKey: ["candidate", "profile", "skills"],
    queryFn: () => candidateApi.list<{ raw_name: string }>("skills"),
  });
  const terms = (skills.data ?? [])
    .slice(0, 3)
    .map((s) => s.raw_name)
    .join(" OR ");
  const recommended = useQuery({
    queryKey: ["jobs", "recommended", terms],
    queryFn: () => api.get<PublicJobs>("/jobs/", { query: { q: terms, page_size: 3 } }),
    enabled: terms.length > 0,
  });

  if (apps.isPending || profile.isPending) return <PageSkeleton />;
  if (apps.isError) return <ErrorState error={apps.error} onRetry={() => apps.refetch()} />;
  const drafts = apps.data.filter((a) => a.status === "draft");
  const active = apps.data.filter(
    (a) =>
      !["draft", "withdrawn", "abandoned", "not_selected", "hired", "offer_declined"].includes(
        a.status,
      ),
  );
  const counts = active.reduce<Record<string, number>>((acc, a) => {
    const s = shownStatus(a.status);
    acc[s] = (acc[s] ?? 0) + 1;
    return acc;
  }, {});
  const completeness = profile.data?.profile_completeness ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>

      <section aria-labelledby="actions" className="flex flex-col gap-2">
        <h2 id="actions" className="text-lg font-semibold">
          {t("actionsTitle")}
        </h2>
        {drafts.length === 0 && completeness >= 60 ? (
          <p className="text-muted-foreground text-sm">{t("noActions")}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {drafts.map((d) => (
              <li
                key={d.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3"
              >
                <span>
                  {t("finishDraft", { title: d.job.title, company: d.job.organisation_name })}
                </span>
                <Button asChild size="sm">
                  <Link href={`/apply/${d.job.id}`}>{t("continue")}</Link>
                </Button>
              </li>
            ))}
            {completeness < 60 ? (
              <li className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
                <span>{t("completeProfile", { value: completeness })}</span>
                <Button asChild size="sm" variant="outline">
                  <Link href="/candidate/profile">{t("openProfile")}</Link>
                </Button>
              </li>
            ) : null}
          </ul>
        )}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("applicationsTitle")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          {active.length === 0 ? (
            <p className="text-muted-foreground">{t("noApplications")}</p>
          ) : (
            <ul className="flex flex-wrap gap-4">
              {Object.entries(counts).map(([s, n]) => (
                <li key={s}>
                  <span className="text-2xl font-semibold">{n}</span>{" "}
                  <span className="text-muted-foreground">{ts.has(s) ? ts(s) : s}</span>
                </li>
              ))}
            </ul>
          )}
          <Link href="/candidate/applications" className="underline">
            {t("allApplications")}
          </Link>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("recommendedTitle")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          {terms.length === 0 ? (
            <p className="text-muted-foreground">
              {t("addSkills")}{" "}
              <Link href="/candidate/profile" className="underline">
                {t("openProfile")}
              </Link>
            </p>
          ) : (recommended.data?.results ?? []).length === 0 ? (
            <p className="text-muted-foreground">
              {t("noRecommended")}{" "}
              <Link href="/jobs" className="underline">
                {t("browse")}
              </Link>
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {recommended.data!.results.map((j) => (
                <li key={j.id}>
                  <Link
                    href={`/jobs/${j.slug}`}
                    className="font-medium underline-offset-2 hover:underline"
                  >
                    {j.title}
                  </Link>{" "}
                  <span className="text-muted-foreground">· {j.organisation.name}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
