"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";

import { CandidateClarifications, CandidateMessages } from "./conversation";
import { EmptyState, ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";

import { candidateApi, type Application } from "../api";
import { useApplication, useApplications, useReview, useTimeline } from "../hooks";
import { ScanChip } from "./documents";

const TERMINAL = new Set(["hired", "not_selected", "withdrawn", "offer_declined", "abandoned"]);
// Candidates see a calmer status vocabulary (internal processing steps are "submitted").
const SHOWN: Record<string, string> = {
  processing: "submitted",
  processing_error: "submitted",
  on_hold: "under_review",
};

export function shownStatus(status: string): string {
  return SHOWN[status] ?? status;
}

function ApplicationRow({ app }: { app: Application }) {
  const t = useTranslations("candidate.applications");
  const format = useFormatter();
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
      <div className="flex flex-col gap-1">
        <Link
          href={`/candidate/applications/${app.id}`}
          className="font-medium underline-offset-2 hover:underline"
        >
          {app.job.title}
        </Link>
        <span className="text-muted-foreground text-sm">
          {app.job.organisation_name}
          {app.reference ? ` · ${app.reference}` : ""}
          {app.submitted_at
            ? ` · ${t("submittedOn", { date: format.dateTime(new Date(app.submitted_at), { dateStyle: "medium" }) })}`
            : ""}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={shownStatus(app.status)} />
        {app.status === "draft" ? (
          <Button asChild size="sm">
            <Link href={`/apply/${app.job.id}`}>{t("continue")}</Link>
          </Button>
        ) : null}
      </div>
    </li>
  );
}

export function CandidateApplications() {
  const t = useTranslations("candidate.applications");
  const apps = useApplications();
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      {apps.isPending ? (
        <PageSkeleton rows={3} />
      ) : apps.isError ? (
        <ErrorState error={apps.error} onRetry={() => apps.refetch()} />
      ) : apps.data.length === 0 ? (
        <EmptyState
          title={t("emptyTitle")}
          description={t("empty")}
          action={
            <Button asChild>
              <Link href="/jobs">{t("browse")}</Link>
            </Button>
          }
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {apps.data.map((a) => (
            <ApplicationRow key={a.id} app={a} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function CandidateApplicationDetail({ id }: { id: string }) {
  const t = useTranslations("candidate.applications");
  const ts = useTranslations("status");
  const format = useFormatter();
  const client = useQueryClient();
  const app = useApplication(id);
  const review = useReview(id, !!app.data && app.data.status !== "draft");
  const timeline = useTimeline(id);
  const [withdrawing, setWithdrawing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const withdraw = useMutation({
    mutationFn: (reason: string) => candidateApi.withdraw(id, reason),
    onSuccess: async () => {
      setWithdrawing(false);
      await client.invalidateQueries({ queryKey: ["candidate", "applications"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : t("failed")),
  });
  if (app.isPending) return <PageSkeleton />;
  if (app.isError) return <ErrorState error={app.error} onRetry={() => app.refetch()} />;
  const a = app.data;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Link
          href="/candidate/applications"
          className="text-muted-foreground text-sm underline-offset-2 hover:underline"
        >
          {t("back")}
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{a.job.title}</h1>
          <StatusBadge status={shownStatus(a.status)} />
        </div>
        <p className="text-muted-foreground">
          {a.job.organisation_name}
          {a.reference ? ` · ${t("reference", { reference: a.reference })}` : ""}
        </p>
        <div className="flex flex-wrap gap-2">
          {a.status === "draft" ? (
            <Button asChild>
              <Link href={`/apply/${a.job.id}`}>{t("continue")}</Link>
            </Button>
          ) : null}
          {!TERMINAL.has(a.status) ? (
            <Button variant="outline" onClick={() => setWithdrawing(true)}>
              {a.status === "draft" ? t("discard") : t("withdraw")}
            </Button>
          ) : null}
          <Button asChild variant="ghost">
            <Link href={`/jobs/${a.job.slug}`}>{t("viewJob")}</Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("timeline")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {timeline.data && timeline.data.length > 0 ? (
            <ol className="flex flex-col gap-3 border-l pl-4">
              {timeline.data.map((e, i) => (
                <li key={`${e.status}-${i}`}>
                  <span className="font-medium">{ts.has(e.status) ? ts(e.status) : e.status}</span>
                  <span className="text-muted-foreground text-sm">
                    {" "}
                    · {format.dateTime(new Date(e.at), { dateStyle: "medium", timeStyle: "short" })}
                  </span>
                  {e.note ? <p className="text-muted-foreground text-sm">{e.note}</p> : null}
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-muted-foreground text-sm">{t("notSubmitted")}</p>
          )}
          <p className="text-muted-foreground mt-4 text-sm">{t("humanReview")}</p>
        </CardContent>
      </Card>

      {review.data ? (
        <Card>
          <CardHeader>
            <CardTitle>
              <h2 className="text-lg font-semibold">{t("whatYouSent")}</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 text-sm">
            <section>
              <h3 className="font-medium">{t("documents")}</h3>
              <ul className="mt-1 flex flex-col gap-1">
                {review.data.documents.map((d) => (
                  <li key={d.document} className="flex items-center gap-2">
                    {d.filename} <ScanChip status={d.scan_status} />
                  </li>
                ))}
              </ul>
            </section>
            {Object.keys(review.data.answers).length > 0 ? (
              <section>
                <h3 className="font-medium">{t("answers")}</h3>
                <dl className="mt-1 grid gap-1 sm:grid-cols-[minmax(0,12rem)_1fr]">
                  {Object.entries(review.data.answers).map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-muted-foreground">{k}</dt>
                      <dd>{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {a.status !== "draft" ? (
        <>
          <CandidateClarifications applicationId={id} />
          <CandidateMessages
            applicationId={id}
            canWrite={!["withdrawn", "abandoned"].includes(a.status)}
          />
        </>
      ) : null}

      {withdrawing ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setWithdrawing(false)}
          title={a.status === "draft" ? t("discardTitle") : t("withdrawTitle")}
          description={a.status === "draft" ? t("discardBody") : t("withdrawBody")}
          confirmLabel={a.status === "draft" ? t("discard") : t("withdraw")}
          destructive
          reason={a.status === "draft" ? "none" : "optional"}
          pending={withdraw.isPending}
          error={error}
          onConfirm={(reason) => withdraw.mutate(reason)}
        />
      ) : null}
    </div>
  );
}

export function CandidateApplicationDetailRoute() {
  const { id } = useParams<{ id: string }>();
  return <CandidateApplicationDetail id={id} />;
}
