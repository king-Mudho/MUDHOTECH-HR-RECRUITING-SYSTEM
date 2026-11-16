"use client";

import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError } from "@/lib/api-client";

import {
  SCREENING_EDITORS,
  useEvaluation,
  useVerifyClaim,
  type CriterionResult,
  type Evaluation,
} from "./api";

interface Category {
  key: string;
  label?: string;
  weight: number;
  score: number | null;
  points: number | null;
}

interface Sentence {
  kind: string;
  criterion_id: string | null;
  text: string;
  citations: { claim_id: string | null; page: number | null; snippet: string }[];
}

const HATCH = "repeating-linear-gradient(45deg, transparent 0 4px, rgb(148 163 184 / 0.5) 4px 6px)";

/** The required label on every AI output. */
export function AiNotice() {
  const t = useTranslations("screening");
  return (
    <p className="text-muted-foreground text-xs" role="note">
      {t("aiNotice")}
    </p>
  );
}

export function BandBadge({ band }: { band: string }) {
  const t = useTranslations("screening.bands");
  return <Badge variant="outline">{t.has(band) ? t(band) : band}</Badge>;
}

/** Category bars (points out of weight); unassessable categories and missing coverage are hatched. */
export function ScoreBreakdown({ evaluation }: { evaluation: Evaluation }) {
  const t = useTranslations("screening.breakdown");
  const categories = evaluation.categories as unknown as Category[];
  const coverage = Math.round((evaluation.coverage ?? 0) * 100);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="text-2xl font-semibold">
          {evaluation.total_score === null ? "—" : t("total", { score: evaluation.total_score })}
        </span>
        <BandBadge band={evaluation.band} />
        <span className="text-muted-foreground text-sm">
          {t("confidence", { level: evaluation.confidence ?? "low" })}
        </span>
      </div>
      <div>
        <div className="flex justify-between text-sm">
          <span>{t("coverage")}</span>
          <span>{coverage}%</span>
        </div>
        <div
          className="mt-1 h-3 w-full overflow-hidden rounded"
          style={{ backgroundImage: HATCH }}
          role="img"
          aria-label={t("coverageAria", { value: coverage })}
        >
          <div className="bg-primary h-full" style={{ width: `${coverage}%` }} />
        </div>
      </div>
      <ul className="flex flex-col gap-2">
        {categories.map((c) => {
          const width = c.score === null ? 0 : Math.max(0, Math.min(100, c.score));
          return (
            <li key={c.key} className="text-sm">
              <div className="flex justify-between">
                <span>{c.label || c.key}</span>
                <span>
                  {c.points === null
                    ? t("notAssessable", { weight: c.weight })
                    : t("points", { points: c.points, weight: c.weight })}
                </span>
              </div>
              <div
                className="bg-muted mt-1 h-2 w-full overflow-hidden rounded"
                style={c.score === null ? { backgroundImage: HATCH } : undefined}
                role="img"
                aria-label={
                  c.points === null
                    ? t("notAssessable", { weight: c.weight })
                    : t("points", { points: c.points, weight: c.weight })
                }
              >
                <div className="bg-primary h-full" style={{ width: `${width}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function VerifyActions({
  appId,
  claimId,
  resultId,
}: {
  appId: string;
  claimId: string;
  resultId: string;
}) {
  const t = useTranslations("screening.verify");
  const verify = useVerifyClaim(appId);
  const [noting, setNoting] = useState(false);
  const [note, setNote] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const noteId = useId();
  const error =
    verify.error instanceof ApiError ? verify.error.message : verify.error ? t("failed") : null;
  const send = (decision: "confirmed" | "rejected") =>
    verify.mutate(
      { claimId, decision, note, reevaluate: true, criterion_result_id: resultId },
      {
        onSuccess: () =>
          setDone(decision === "confirmed" ? t("confirmedDone") : t("notSupportedDone")),
      },
    );
  if (done)
    return (
      <p role="status" className="text-muted-foreground text-xs">
        {done}
      </p>
    );
  return (
    <div className="mt-1 flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={verify.isPending}
          onClick={() => send("confirmed")}
        >
          {t("confirm")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={verify.isPending}
          onClick={() => setNoting(true)}
        >
          {t("notSupported")}
        </Button>
      </div>
      {noting ? (
        <div className="flex flex-col gap-1">
          <Label htmlFor={noteId}>{t("noteLabel")}</Label>
          <Input id={noteId} value={note} onChange={(e) => setNote(e.target.value)} />
          <Button
            size="sm"
            className="self-start"
            disabled={verify.isPending || note.trim().length < 3}
            onClick={() => send("rejected")}
          >
            {t("save")}
          </Button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="text-destructive text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** One row per criterion: status, method, confidence, cited evidence and verify actions. */
export function CriteriaPanel({
  appId,
  evaluation,
  canVerify,
}: {
  appId: string;
  evaluation: Evaluation;
  canVerify: boolean;
}) {
  const t = useTranslations("screening.criteria");
  const ts = useTranslations("screening.status");
  const row = (c: CriterionResult) => (
    <li key={c.id} id={`criterion-${c.criterion_id}`} className="rounded-md border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{c.title}</span>
        {c.importance === "essential" ? <Badge>{t("essential")}</Badge> : null}
        <Badge variant="outline">
          {ts.has(c.evidence_status) ? ts(c.evidence_status) : c.evidence_status}
        </Badge>
        <span className="text-muted-foreground ml-auto">
          {c.score === null ? t("unknown") : t("score", { score: c.score })}
        </span>
      </div>
      <p className="text-muted-foreground mt-1 text-xs">
        {t("meta", { method: c.match_method, confidence: Math.round(c.confidence * 100) })}
      </p>
      {c.evidence.length ? (
        <ul className="mt-2 flex flex-col gap-2">
          {c.evidence.map((e, i) => (
            <li key={`${e.claim_id ?? e.question_response_id}-${i}`}>
              <blockquote className="text-muted-foreground border-l-2 pl-2 text-xs">
                {e.page ? t("page", { page: e.page }) : t("answer")} “{e.snippet}”
              </blockquote>
              {canVerify && e.claim_id && c.evidence_status !== "human_verified" ? (
                <VerifyActions appId={appId} claimId={e.claim_id} resultId={c.id} />
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground mt-2 text-xs">{t("noEvidence")}</p>
      )}
    </li>
  );
  return <ul className="flex flex-col gap-2">{evaluation.criteria.map(row)}</ul>;
}

/** Explanation sentences; each citation jumps to the criterion's evidence. */
export function ExplanationList({ evaluation }: { evaluation: Evaluation }) {
  const t = useTranslations("screening.explanation");
  const sentences = evaluation.explanation as unknown as Sentence[];
  if (!sentences.length) return null;
  return (
    <ol className="flex list-decimal flex-col gap-1 pl-5 text-sm">
      {sentences.map((s, i) => (
        <li key={i}>
          {s.text}{" "}
          {s.criterion_id && s.citations.length ? (
            <a
              href={`#criterion-${s.criterion_id}`}
              className="text-primary text-xs underline"
              aria-label={t("citationAria", { count: s.citations.length })}
            >
              [{t("citations", { count: s.citations.length })}]
            </a>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

/** AI-assisted evaluation on the HR application page. */
export function EvaluationPanel({ appId }: { appId: string }) {
  const t = useTranslations("screening.panel");
  const { role } = useJobsContext();
  const evaluation = useEvaluation(appId);
  return (
    <section aria-labelledby="hr-evaluation" className="rounded-lg border p-4">
      <h2 id="hr-evaluation" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <AiNotice />
      {evaluation.isPending ? (
        <PageSkeleton rows={2} />
      ) : evaluation.isError ? (
        <ErrorState error={evaluation.error} onRetry={() => evaluation.refetch()} />
      ) : evaluation.data === null ? (
        <p className="text-muted-foreground mt-2 text-sm">{t("none")}</p>
      ) : evaluation.data.band === "manual_review_requested" ? (
        <Alert className="mt-2">
          <AlertDescription>{t("manual")}</AlertDescription>
        </Alert>
      ) : (
        <div className="mt-3 flex flex-col gap-4">
          <p className="text-muted-foreground text-xs">
            {t("version", { version: evaluation.data.version })}
          </p>
          <ScoreBreakdown evaluation={evaluation.data} />
          <div>
            <h3 className="mb-2 text-sm font-semibold">{t("why")}</h3>
            <ExplanationList evaluation={evaluation.data} />
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold">{t("criteria")}</h3>
            <CriteriaPanel
              appId={appId}
              evaluation={evaluation.data}
              canVerify={SCREENING_EDITORS.includes(role ?? "")}
            />
          </div>
        </div>
      )}
    </section>
  );
}
