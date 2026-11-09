"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, Loader2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useFormatter, useNow, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

import type { JobDetail, jobsApi } from "../api";
import { canJob, jobKeys, useJob, useJobsContext } from "../hooks";
import { ReadinessPanel } from "./readiness-panel";
import { DetailsStep } from "./step-details";
import { PreviewStep } from "./step-preview";
import { QuestionsStep } from "./step-questions";
import { RequirementsStep } from "./step-requirements";
import { RubricStep } from "./step-rubric";
import {
  STEPS,
  WizardContext,
  type SaveState,
  type Step,
  type WizardContextValue,
} from "./wizard-context";

function SaveIndicator({ state }: { state: SaveState }) {
  const t = useTranslations("jobs.wizard.save");
  const format = useFormatter();
  const now = useNow({ updateInterval: 5000 });
  let body: ReactNode = null;
  if (state.kind === "saving")
    body = (
      <>
        <Loader2 aria-hidden="true" className="size-4 animate-spin" />
        {t("saving")}
      </>
    );
  else if (state.kind === "saved")
    body = (
      <>
        <Check aria-hidden="true" className="text-success size-4" />
        {t("saved", { when: format.relativeTime(new Date(state.at), now) })}
      </>
    );
  else if (state.kind === "error")
    body = (
      <>
        <CircleAlert aria-hidden="true" className="text-destructive size-4" />
        {t("failed")}
      </>
    );
  return (
    <p
      role="status"
      aria-live="polite"
      className="text-muted-foreground flex min-h-6 items-center gap-1.5 text-sm"
    >
      {body}
    </p>
  );
}

export function JobWizard({ jobId }: { jobId?: string }) {
  const t = useTranslations("jobs.wizard");
  const { role, isPending: ctxPending, orgId, api } = useJobsContext();
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const requested = search.get("step") as Step | null;
  const step: Step = jobId && requested && STEPS.includes(requested) ? requested : "details";
  const job = useJob(jobId);

  if (ctxPending || (jobId && job.isPending)) return <PageSkeleton />;
  if (!orgId || !api || !canJob(role, "jobs.create"))
    return <ForbiddenState description={t("forbidden")} />;
  if (!jobId) {
    return (
      <div className="flex flex-col gap-4">
        <WizardHeader title={t("newTitle")} />
        <StepNav current="details" jobId={undefined} />
        <DetailsStep
          onCreated={(created) => router.replace(`/hr/jobs/${created.id}/edit?step=requirements`)}
        />
      </div>
    );
  }
  if (job.isError) {
    const e = job.error;
    if (e instanceof ApiError && e.status === 404)
      return <ForbiddenState title={t("notFoundTitle")} description={t("notFound")} />;
    return <ErrorState error={e} onRetry={() => job.refetch()} />;
  }
  return (
    <EditWizard
      job={job.data!}
      api={api}
      role={role}
      step={step}
      goTo={(s) => router.push(`${pathname}?step=${s}`, { scroll: true })}
    />
  );
}

function WizardHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children}
    </div>
  );
}

function StepNav({ current, jobId }: { current: Step; jobId: string | undefined }) {
  const t = useTranslations("jobs.wizard.steps");
  const tw = useTranslations("jobs.wizard");
  return (
    <nav aria-label={tw("stepsLabel")}>
      <ol className="flex flex-wrap gap-2 text-sm">
        {STEPS.map((s, i) => {
          const active = s === current;
          const label = `${i + 1}. ${t(s)}`;
          return (
            <li key={s}>
              {jobId ? (
                <Link
                  href={`/hr/jobs/${jobId}/edit?step=${s}`}
                  aria-current={active ? "step" : undefined}
                  className={cn(
                    "inline-flex min-h-9 items-center rounded-full border px-3",
                    active ? "bg-primary text-primary-foreground border-primary" : "hover:bg-muted",
                  )}
                >
                  {label}
                </Link>
              ) : (
                <span
                  aria-current={active ? "step" : undefined}
                  aria-disabled={!active || undefined}
                  className={cn(
                    "inline-flex min-h-9 items-center rounded-full border px-3",
                    active
                      ? "bg-primary text-primary-foreground border-primary"
                      : "text-muted-foreground",
                  )}
                >
                  {label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function EditWizard({
  job,
  api,
  role,
  step,
  goTo,
}: {
  job: JobDetail;
  api: ReturnType<typeof jobsApi>;
  role: string | null;
  step: Step;
  goTo: (step: Step) => void;
}) {
  const t = useTranslations("jobs.wizard");
  const client = useQueryClient();
  const { orgId } = useJobsContext();
  const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" });
  const [resetToken, setResetToken] = useState(0);
  const lockRef = useRef(job.lock_version);
  useEffect(() => {
    lockRef.current = job.lock_version;
  }, [job.lock_version]);

  const save = useCallback<WizardContextValue["save"]>(
    async (fn) => {
      setSaveState({ kind: "saving" });
      try {
        const updated = await fn(lockRef.current);
        lockRef.current = updated.lock_version;
        client.setQueryData(jobKeys.detail(orgId!, job.id), updated);
        void client.invalidateQueries({
          queryKey: [...jobKeys.detail(orgId!, job.id), "readiness"],
        });
        void client.invalidateQueries({
          queryKey: jobKeys.all(orgId!),
          exact: false,
          refetchType: "none",
        });
        setSaveState({ kind: "saved", at: Date.now() });
        return updated;
      } catch (err) {
        if (err instanceof ApiError && err.code === "conflict.stale_version")
          setSaveState({ kind: "conflict" });
        else
          setSaveState({
            kind: "error",
            message: err instanceof ApiError ? err.message : t("save.failed"),
          });
        return err instanceof ApiError ? err : new ApiError(0, "unknown", String(err));
      }
    },
    [client, orgId, job.id, t],
  );

  const reloadLatest = async () => {
    await client.invalidateQueries({ queryKey: jobKeys.detail(orgId!, job.id) });
    setResetToken((n) => n + 1);
    setSaveState({ kind: "idle" });
  };

  const editable = job.version?.status === "draft";
  const value: WizardContextValue = { job, api, role, save, saveState, goTo, resetToken };

  return (
    <WizardContext.Provider value={value}>
      <div className="flex flex-col gap-4">
        <WizardHeader title={job.title}>
          <div className="flex items-center gap-3">
            <StatusBadge status={job.status} />
            <SaveIndicator state={saveState} />
            <Button asChild variant="outline" className="min-h-10">
              <Link href={`/hr/jobs/${job.id}`}>{t("overview")}</Link>
            </Button>
          </div>
        </WizardHeader>
        <StepNav current={step} jobId={job.id} />
        {saveState.kind === "conflict" ? (
          <Alert variant="destructive" role="alert">
            <AlertTitle>{t("conflictTitle")}</AlertTitle>
            <AlertDescription className="flex flex-col gap-2">
              <p>{t("conflictBody")}</p>
              <div>
                <Button variant="outline" onClick={reloadLatest}>
                  {t("reloadLatest")}
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        ) : null}
        {saveState.kind === "error" ? (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{saveState.message}</AlertDescription>
          </Alert>
        ) : null}
        {!editable ? (
          <Alert role="status">
            <AlertTitle>{t("lockedTitle")}</AlertTitle>
            <AlertDescription>
              {t("lockedBody")}{" "}
              <Link href={`/hr/jobs/${job.id}`} className="underline">
                {t("overview")}
              </Link>
            </AlertDescription>
          </Alert>
        ) : null}
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <fieldset disabled={!editable} className="min-w-0">
            <legend className="sr-only">{t(`steps.${step}`)}</legend>
            {step === "details" ? <DetailsStep key={resetToken} /> : null}
            {step === "requirements" ? <RequirementsStep key={resetToken} /> : null}
            {step === "questions" ? <QuestionsStep key={resetToken} /> : null}
            {step === "rubric" ? <RubricStep key={resetToken} /> : null}
            {step === "preview" ? <PreviewStep /> : null}
          </fieldset>
          <aside aria-label={t("readinessLabel")} className="lg:sticky lg:top-4 lg:self-start">
            <ReadinessPanel jobId={job.id} stage="submit" compact />
          </aside>
        </div>
      </div>
    </WizardContext.Provider>
  );
}
