"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { TextField } from "@/components/forms/form-field";
import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { applyServerErrors } from "@/features/auth/form-errors";
import { candidateKeys } from "@/features/candidates/hooks";
import { ApiError } from "@/lib/api-client";

import {
  GROUPS,
  grouped,
  resumeKeys,
  resumesApi,
  useApplicationExtraction,
  useResumePreview,
  type ApplicationClaim,
  type ClaimView,
  type ResumeExtraction,
} from "../api";

const READING = new Set(["pending", "running"]);
const NOTICE_FLAGS = [
  "possibly_not_cv",
  "language_unsupported",
  "low_ocr_confidence",
  "ocr_unavailable",
  "hidden_text",
] as const;

function ClaimLine({ claim, action }: { claim: ClaimView; action?: React.ReactNode }) {
  const t = useTranslations("extraction");
  return (
    <li className="flex flex-wrap items-start justify-between gap-2 rounded-md border p-3 text-sm">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="font-medium">{claim.title || t("untitled")}</span>
        {claim.subtitle || claim.dates ? (
          <span className="text-muted-foreground">
            {[claim.subtitle, claim.dates].filter(Boolean).join(" · ")}
          </span>
        ) : null}
        {claim.detail ? <span className="text-muted-foreground">{claim.detail}</span> : null}
        {claim.snippet ? (
          <span className="text-muted-foreground text-xs">
            {t("from", { page: claim.page ?? 1 })} “{claim.snippet}”
          </span>
        ) : null}
      </div>
      {action}
    </li>
  );
}

function Notices({ flags }: { flags: string[] }) {
  const t = useTranslations("extraction.flags");
  const shown = NOTICE_FLAGS.filter((f) => flags.includes(f));
  if (!shown.length) return null;
  return (
    <Alert>
      <AlertTitle>{t("title")}</AlertTitle>
      <AlertDescription>
        <ul className="list-disc pl-5">
          {shown.map((f) => (
            <li key={f}>{t(f)}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function Ignored({ claims }: { claims: ClaimView[] }) {
  const t = useTranslations("extraction");
  if (!claims.length) return null;
  const personal = [...new Set(claims.filter((c) => c.type === "protected").map((c) => c.title))];
  const other = claims.filter((c) => c.type !== "protected").length;
  return (
    <section aria-labelledby="extraction-ignored" className="rounded-md border p-3 text-sm">
      <h4 id="extraction-ignored" className="font-medium">
        {t("ignoredTitle")}
      </h4>
      {personal.length ? (
        <p className="mt-1">{t("ignoredPersonal", { items: personal.join(", ") })}</p>
      ) : null}
      {other ? <p className="mt-1">{t("ignoredOther", { count: other })}</p> : null}
    </section>
  );
}

/** Grouped claims; ``renderAction`` adds a per-claim button (e.g. "Correct"). */
function ClaimGroups<T extends ClaimView>({
  claims,
  renderAction,
}: {
  claims: T[];
  renderAction?: (claim: T) => React.ReactNode;
}) {
  const t = useTranslations("extraction");
  const { byType, summary, ignored } = grouped(claims);
  const any = GROUPS.some((g) => byType[g].length);
  return (
    <div className="flex flex-col gap-4">
      {summary?.detail ? <p className="text-sm">{summary.detail}</p> : null}
      {!any ? <p className="text-muted-foreground text-sm">{t("nothingFound")}</p> : null}
      {GROUPS.map((g) =>
        byType[g].length ? (
          <section key={g} aria-label={t(`groups.${g}`)}>
            <h4 className="mb-2 text-sm font-semibold">{t(`groups.${g}`)}</h4>
            {g === "skill" || g === "language" ? (
              <ul className="flex flex-wrap gap-2">
                {byType[g].map((c) => (
                  <li key={`${c.type}-${c.index}`} className="flex items-center gap-1">
                    <Badge variant="secondary" title={c.snippet || undefined}>
                      {c.title}
                      {c.detail ? ` (${c.detail})` : ""}
                    </Badge>
                    {renderAction?.(c)}
                  </li>
                ))}
              </ul>
            ) : (
              <ul className="flex flex-col gap-2">
                {byType[g].map((c) => (
                  <ClaimLine key={`${c.type}-${c.index}`} claim={c} action={renderAction?.(c)} />
                ))}
              </ul>
            )}
          </section>
        ) : null,
      )}
      <Ignored claims={ignored} />
    </div>
  );
}

function Reading() {
  const t = useTranslations("extraction");
  return (
    <p role="status" aria-live="polite" className="text-muted-foreground text-sm">
      {t("reading")}
    </p>
  );
}

function Failed({ code }: { code: string }) {
  const t = useTranslations("extraction.failed");
  return (
    <Alert variant="destructive">
      <AlertTitle>{t("title")}</AlertTitle>
      <AlertDescription>{t.has(code) ? t(code) : t("other")}</AlertDescription>
    </Alert>
  );
}

/** "What we extracted from your CV" for one of the candidate's CVs (wizard + documents page). */
export function ResumeExtractionView({
  documentId,
  allowImport = false,
}: {
  documentId: string;
  allowImport?: boolean;
}) {
  const t = useTranslations("extraction");
  const preview = useResumePreview(documentId);
  const [importing, setImporting] = useState(false);
  if (preview.isPending) return <PageSkeleton rows={2} />;
  if (preview.isError)
    return <ErrorState error={preview.error} onRetry={() => preview.refetch()} />;
  const data = preview.data;
  if (READING.has(data.status)) return <Reading />;
  if (data.status === "failed") return <Failed code={data.error_code} />;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-muted-foreground text-sm">{t("explain")}</p>
      <Notices flags={data.flags} />
      <ClaimGroups claims={data.claims} />
      {allowImport ? (
        <div>
          <Button type="button" variant="outline" onClick={() => setImporting(true)}>
            {t("import.open")}
          </Button>
          {data.imported_at ? (
            <span className="text-muted-foreground ml-2 text-xs">{t("import.done")}</span>
          ) : null}
        </div>
      ) : null}
      {importing ? (
        <ImportDialog documentId={documentId} data={data} onClose={() => setImporting(false)} />
      ) : null}
    </div>
  );
}

function ImportDialog({
  documentId,
  data,
  onClose,
}: {
  documentId: string;
  data: ResumeExtraction;
  onClose: () => void;
}) {
  const t = useTranslations("extraction.import");
  const tg = useTranslations("extraction.groups");
  const client = useQueryClient();
  const importable = data.claims.filter(
    (c) =>
      !c.excluded &&
      ["experience", "education", "certification", "skill", "language"].includes(c.type),
  );
  const [chosen, setChosen] = useState<Set<number>>(() => new Set(importable.map((c) => c.index)));
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirmId = useId();
  const run = useMutation({
    mutationFn: () => resumesApi.importToProfile(documentId, [...chosen]),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: candidateKeys.profile });
      void client.invalidateQueries({ queryKey: resumeKeys.preview(documentId) });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : t("failed")),
  });
  const toggle = (i: number) =>
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("body")}</DialogDescription>
        </DialogHeader>
        <fieldset className="flex flex-col gap-2">
          <legend className="sr-only">{t("choose")}</legend>
          {importable.map((c) => {
            const id = `import-${c.index}`;
            return (
              <div key={id} className="flex items-start gap-2 text-sm">
                <input
                  id={id}
                  type="checkbox"
                  className="mt-1 size-4"
                  checked={chosen.has(c.index)}
                  onChange={() => toggle(c.index)}
                />
                <Label htmlFor={id} className="font-normal">
                  <span className="text-muted-foreground">{tg(c.type as never)}: </span>
                  {c.title}
                  {c.subtitle ? ` · ${c.subtitle}` : ""}
                </Label>
              </div>
            );
          })}
        </fieldset>
        <div className="flex items-start gap-2 text-sm">
          <input
            id={confirmId}
            type="checkbox"
            className="mt-1 size-4"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          <Label htmlFor={confirmId} className="font-normal">
            {t("confirm")}
          </Label>
        </div>
        {error ? (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button
            type="button"
            disabled={!confirmed || chosen.size === 0 || run.isPending}
            onClick={() => run.mutate()}
          >
            {t("submit", { count: chosen.size })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ submitted applications
const FIELDS: Record<string, string[]> = {
  experience: ["title", "employer", "location", "start", "end"],
  education: ["qualification_text", "institution", "year", "grade"],
  certification: ["name", "body", "issued"],
  skill: ["name", "years"],
  language: ["language", "level"],
};

const correctionSchema = z
  .object({
    values: z.record(z.string(), z.string().max(300, "tooLong")),
    remove: z.boolean(),
    note: z.string().max(1000, "tooLong"),
  })
  .refine((v) => v.remove || Object.values(v.values).some((x) => x.trim()), {
    message: "correctionEmpty",
    path: ["note"],
  });
type CorrectionValues = z.infer<typeof correctionSchema>;

function CorrectionDialog({
  applicationId,
  claim,
  onClose,
}: {
  applicationId: string;
  claim: ApplicationClaim;
  onClose: () => void;
}) {
  const t = useTranslations("extraction.correct");
  const client = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const fields = FIELDS[claim.type] ?? [];
  const form = useForm<CorrectionValues>({
    resolver: zodResolver(correctionSchema),
    defaultValues: {
      values: Object.fromEntries(fields.map((f) => [f, ""])),
      remove: false,
      note: "",
    },
  });
  const { register, handleSubmit, formState, setError, control } = form;
  const removing = useWatch({ control, name: "remove" });
  const save = useMutation({
    mutationFn: (v: CorrectionValues) =>
      resumesApi.correct(claim.id, {
        values: Object.fromEntries(Object.entries(v.values).filter(([, x]) => x.trim())),
        remove: v.remove,
        note: v.note,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: resumeKeys.application(applicationId) });
      onClose();
    },
    onError: (err) => setFormError(applyServerErrors(err, setError, { note: "note" })),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("title", { item: claim.title })}</DialogTitle>
          <DialogDescription>{t("body")}</DialogDescription>
        </DialogHeader>
        <form
          method="post"
          noValidate
          className="flex flex-col gap-3"
          onSubmit={handleSubmit((v) => {
            setFormError(null);
            save.mutate(v);
          })}
        >
          <div className="flex items-start gap-2 text-sm">
            <input
              id="correct-remove"
              type="checkbox"
              className="mt-1 size-4"
              {...register("remove")}
            />
            <Label htmlFor="correct-remove" className="font-normal">
              {t("remove")}
            </Label>
          </div>
          {!removing
            ? fields.map((f) => (
                <TextField
                  key={f}
                  label={t(`fields.${f}` as never)}
                  placeholder={t("keepBlank")}
                  {...register(`values.${f}`)}
                  error={formState.errors.values?.[f]}
                />
              ))
            : null}
          <TextField
            label={t("note")}
            {...register("note")}
            error={formState.errors.note}
            description={t("noteHelp")}
          />
          {formError ? (
            <Alert variant="destructive" role="alert">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("cancel")}
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {t("submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** What the employer's system read from the CVs of a submitted application, with corrections. */
export function ApplicationExtractionView({ applicationId }: { applicationId: string }) {
  const t = useTranslations("extraction");
  const view = useApplicationExtraction(applicationId);
  const [correcting, setCorrecting] = useState<ApplicationClaim | null>(null);
  if (view.isPending) return <PageSkeleton rows={2} />;
  if (view.isError) return <ErrorState error={view.error} onRetry={() => view.refetch()} />;
  const data = view.data;
  if (data.objected) return <p className="text-muted-foreground text-sm">{t("objected")}</p>;
  if (!data.runs.length) return <Reading />;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground text-sm">{t("explainApplication")}</p>
      {data.runs.map((run) => (
        <div key={run.document_id} className="flex flex-col gap-3">
          <h4 className="text-sm font-semibold">{run.filename}</h4>
          {READING.has(run.status) ? (
            <Reading />
          ) : run.status === "failed" ? (
            <Failed code={run.error_code} />
          ) : (
            <>
              <Notices flags={run.flags} />
              <ClaimGroups
                claims={run.claims}
                renderAction={(c) =>
                  c.correctable ? (
                    <span className="flex items-center gap-1">
                      {c.corrections.length ? (
                        <Badge variant="outline">{t("correct.sent")}</Badge>
                      ) : null}
                      <Button
                        type="button"
                        size="sm"
                        variant="link"
                        className="h-auto p-0"
                        aria-label={t("correct.open", { item: c.title })}
                        onClick={() => setCorrecting(c)}
                      >
                        {t("correct.button")}
                      </Button>
                    </span>
                  ) : null
                }
              />
            </>
          )}
        </div>
      ))}
      {correcting ? (
        <CorrectionDialog
          applicationId={applicationId}
          claim={correcting}
          onClose={() => setCorrecting(null)}
        />
      ) : null}
    </div>
  );
}
