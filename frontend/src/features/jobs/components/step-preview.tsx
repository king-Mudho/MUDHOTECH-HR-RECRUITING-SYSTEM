"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";

import { canJob, jobKeys, useJobsContext } from "../hooks";
import { ReadinessPanel } from "./readiness-panel";
import { StepFooter, useWizard } from "./wizard-context";

/** Candidate-facing preview + readiness checklist + submit for approval. */
export function PreviewStep() {
  const t = useTranslations("jobs.preview");
  const tc = useTranslations("jobs.choices");
  const format = useFormatter();
  const router = useRouter();
  const client = useQueryClient();
  const { orgId } = useJobsContext();
  const { job, api, role } = useWizard();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const v = job.version;
  const essential = job.criteria.filter((c) => c.importance === "essential");
  const preferred = job.criteria.filter((c) => c.importance === "preferred");

  const submit = async () => {
    setPending(true);
    setError(null);
    try {
      await api.action(job.id, "submit-for-approval");
      await client.invalidateQueries({ queryKey: jobKeys.all(orgId!) });
      router.push(`/hr/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("submitFailed"));
      await client.invalidateQueries({
        queryKey: [...jobKeys.detail(orgId!, job.id), "readiness"],
      });
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-xl font-semibold">{job.title}</h2>
          </CardTitle>
          <p className="text-muted-foreground text-sm">
            {tc(`employment.${job.employment_type}`)} · {tc(`workplace.${job.workplace_type}`)}
            {job.closes_at
              ? ` · ${t("closes", {
                  date: format.dateTime(new Date(job.closes_at), {
                    dateStyle: "long",
                    timeStyle: "short",
                    timeZone: job.timezone,
                  }),
                  tz: job.timezone,
                })}`
              : ""}
          </p>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 text-sm">
          {v?.summary ? <p>{v.summary}</p> : null}
          {/* HTML below was sanitised by the server allow-list on save (EC-JOB-12). */}
          {(["responsibilities_html", "requirements_html", "benefits_html"] as const).map((name) =>
            v?.[name] ? (
              <section key={name}>
                <h3 className="mb-1 font-semibold">{t(name)}</h3>
                <div
                  className="[&_a]:underline [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5"
                  dangerouslySetInnerHTML={{ __html: v[name] }}
                />
              </section>
            ) : null,
          )}
          <section>
            <h3 className="mb-1 font-semibold">{t("essential")}</h3>
            {essential.length ? (
              <ul className="list-disc pl-5">
                {essential.map((c) => (
                  <li key={c.id}>{c.title}</li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">{t("none")}</p>
            )}
          </section>
          <section>
            <h3 className="mb-1 font-semibold">{t("preferred")}</h3>
            {preferred.length ? (
              <ul className="list-disc pl-5">
                {preferred.map((c) => (
                  <li key={c.id}>{c.title}</li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">{t("none")}</p>
            )}
          </section>
          <section>
            <h3 className="mb-1 font-semibold">
              {t("questions", { count: job.questions.length })}
            </h3>
            <ol className="list-decimal pl-5">
              {job.questions.map((q) => (
                <li key={q.id}>{q.prompt}</li>
              ))}
            </ol>
          </section>
        </CardContent>
      </Card>
      <ReadinessPanel jobId={job.id} stage="submit" />
      {error ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {canJob(role, "jobs.create") && v?.status === "draft" ? (
        <div className="flex justify-end">
          <Button className="min-h-10" disabled={pending} onClick={() => void submit()}>
            {pending ? t("submitting") : t("submit")}
          </Button>
        </div>
      ) : null}
      <StepFooter step="preview" />
    </div>
  );
}
