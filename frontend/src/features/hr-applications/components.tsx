"use client";

import { Download } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";

import { ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScanChip } from "@/features/candidates/components/documents";
import { documentsApi } from "@/features/documents/api";
import { useJobsContext } from "@/features/jobs/hooks";
import { ReviewWorkspace } from "@/features/screening/review-workspace";
import { ApiError } from "@/lib/api-client";
import { downloadWithOrg } from "@/lib/download";

import { APPLICATION_VIEWERS, useHRApplication } from "./api";
import { ApplicantsTable } from "./applicants";
import { DeclareConflict } from "./declare-conflict";
import { ExtractionPanel } from "./extraction-panel";
import { ActionsPanel, ClarificationsPanel, MessagesPanel, NotesPanel } from "./panels";
import { RevealIdentity } from "./reveal-identity";

function Denied({ error }: { error: unknown }) {
  const t = useTranslations("hrApplications");
  if (error instanceof ApiError && error.status === 404)
    return <ForbiddenState title={t("notFoundTitle")} description={t("notFound")} />;
  if (error instanceof ApiError && error.status === 403)
    return <ForbiddenState description={t("forbidden")} />;
  return <ErrorState error={error} />;
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
  const tf = useTranslations("hrApplications.extraction.flags");
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

      {a.flags.length ? (
        <Alert role="status">
          <AlertTitle>{t("detail.flagsTitle")}</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {a.flags.map((f) => (
                <li key={f}>{tf.has(f) ? tf(f) : f}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-wrap justify-end gap-2">
        {["org_admin", "hr_manager"].includes(role) ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              void downloadWithOrg(
                `/api/v1/hr/applications/${a.id}/reconstruct.pdf`,
                orgId,
                `reconstruction-${a.reference ?? a.id}.pdf`,
              )
            }
          >
            {t("detail.reconstruct")}
          </Button>
        ) : null}
        <DeclareConflict applicationId={a.id} jobId={a.job.id} />
      </div>
      <ActionsPanel app={a} />

      <section aria-labelledby="hr-contact" className="rounded-lg border p-4">
        <h2 id="hr-contact" className="text-lg font-semibold">
          {t("detail.contact")}
        </h2>
        {a.identity_hidden ? (
          <div className="mt-2">
            <RevealIdentity applicationId={a.id} />
          </div>
        ) : (
          <dl className="mt-2 grid gap-1 text-sm sm:grid-cols-[10rem_1fr]">
            {contactRows.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-muted-foreground">{label}</dt>
                <dd>{formatValue(value)}</dd>
              </div>
            ))}
          </dl>
        )}
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

      <ReviewWorkspace appId={a.id} jobId={a.job.id} />
      <ExtractionPanel app={a} />

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
      <NotesPanel app={a} />
      <ClarificationsPanel app={a} />
      <MessagesPanel app={a} />
    </div>
  );
}

export function JobApplicationsRoute() {
  const { id } = useParams<{ id: string }>();
  return <ApplicantsTable jobId={id} />;
}

export function HRApplicationRoute() {
  const { id } = useParams<{ id: string }>();
  return <HRApplicationView id={id} />;
}

export { ApplicantsTable as JobApplicationsList };
