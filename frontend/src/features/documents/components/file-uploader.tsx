"use client";

import { CheckCircle2, CircleAlert, FileText, Loader2, RotateCcw, Upload, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

import { documentsApi, putWithProgress, type UploadPurpose, type UploadedDocument } from "../api";

const ACCEPT: Record<UploadPurpose, string> = {
  cv: ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  supporting: ".pdf,.docx,.jpg,.jpeg,.png",
  message_attachment: ".pdf,.docx,.jpg,.jpeg,.png",
  offer_letter: ".pdf",
};
const MAX_MB = 10;
const POLL_MS = 2000;
const POLL_LIMIT = 60; // ~2 minutes; scanning continues server-side either way

type Phase =
  | { kind: "idle" }
  | { kind: "uploading"; progress: number; name: string }
  | { kind: "checking"; name: string }
  | { kind: "done"; doc: UploadedDocument }
  | { kind: "error"; message: string; name?: string; file?: File };

/**
 * Upload one file safely (FR-M07-02): presigned PUT with progress -> confirm -> poll the security
 * scan. Falls back to a direct upload when the storage PUT is blocked, supports cancel and retry,
 * and announces every state change to screen readers (EC-APP-20: resumable, progress shown).
 */
export function FileUploader({
  purpose,
  label,
  description,
  onUploaded,
  disabled = false,
}: {
  purpose: UploadPurpose;
  label: string;
  description?: string;
  onUploaded: (doc: UploadedDocument) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("documents.uploader");
  const inputId = useId();
  const descId = useId();
  const statusId = useId();
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => () => abortRef.current?.abort(), []);

  const poll = async (doc: UploadedDocument, signal: AbortSignal): Promise<UploadedDocument> => {
    let current = doc;
    for (let i = 0; i < POLL_LIMIT && current.scan_status === "pending"; i++) {
      await new Promise((r) => setTimeout(r, POLL_MS));
      if (signal.aborted) throw new DOMException("Aborted", "AbortError");
      current = await documentsApi.get(doc.id);
    }
    return current;
  };

  const upload = async (file: File) => {
    if (file.size > MAX_MB * 1024 * 1024) {
      setPhase({ kind: "error", message: t("tooLarge", { mb: MAX_MB }), name: file.name });
      return;
    }
    const controller = new AbortController();
    abortRef.current?.abort();
    abortRef.current = controller;
    setPhase({ kind: "uploading", progress: 0, name: file.name });
    try {
      const mime = file.type || "application/octet-stream";
      let doc: UploadedDocument;
      try {
        const session = await documentsApi.createSession({
          purpose,
          filename: file.name,
          mime,
          size: file.size,
        });
        await putWithProgress(
          session.url,
          file,
          session.headers,
          (p) => setPhase({ kind: "uploading", progress: p, name: file.name }),
          controller.signal,
        );
        doc = await documentsApi.complete(session.id);
      } catch (err) {
        // Storage unreachable from this network: send through the API instead.
        if (err instanceof ApiError && (err.status === 0 || err.code === "upload_failed")) {
          doc = await documentsApi.directUpload(purpose, file);
        } else {
          throw err;
        }
      }
      setPhase({ kind: "checking", name: file.name });
      const checked = await poll(doc, controller.signal);
      if (
        checked.scan_status === "clean" ||
        checked.scan_status === "skipped" ||
        checked.scan_status === "pending"
      ) {
        setPhase({ kind: "done", doc: checked });
        onUploaded(checked);
      } else {
        setPhase({
          kind: "error",
          message: t(`reasons.${checked.rejected_reason || "other"}`),
          name: file.name,
        });
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setPhase({ kind: "idle" });
        return;
      }
      setPhase({
        kind: "error",
        message: err instanceof ApiError ? err.message : t("failed"),
        name: file.name,
        file, // transfer failures can be retried; rejected content cannot
      });
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const busy = phase.kind === "uploading" || phase.kind === "checking";
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={inputId} className="text-sm font-medium">
        {label}
      </label>
      {description ? (
        <p id={descId} className="text-muted-foreground text-xs">
          {description}
        </p>
      ) : null}
      <div
        className={cn(
          "flex flex-col gap-3 rounded-lg border border-dashed p-4",
          phase.kind === "error" && "border-destructive/60",
        )}
      >
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            accept={ACCEPT[purpose]}
            disabled={disabled || busy}
            aria-describedby={[description ? descId : null, statusId].filter(Boolean).join(" ")}
            className="file:bg-primary file:text-primary-foreground text-sm file:mr-3 file:min-h-10 file:rounded-md file:border-0 file:px-3"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          {busy ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => abortRef.current?.abort()}
            >
              <X aria-hidden="true" />
              {t("cancel")}
            </Button>
          ) : null}
          {phase.kind === "error" && phase.file ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void upload(phase.file!)}
            >
              <RotateCcw aria-hidden="true" />
              {t("retry")}
            </Button>
          ) : null}
        </div>
        {phase.kind === "uploading" ? (
          <div
            role="progressbar"
            aria-label={t("progressLabel", { name: phase.name })}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(phase.progress * 100)}
            className="bg-muted h-2 w-full overflow-hidden rounded-full"
          >
            <div
              className="bg-primary h-full transition-[width]"
              style={{ width: `${Math.round(phase.progress * 100)}%` }}
            />
          </div>
        ) : null}
        <p
          id={statusId}
          role="status"
          aria-live="polite"
          className="flex min-h-6 items-center gap-2 text-sm"
        >
          {phase.kind === "idle" ? (
            <>
              <Upload aria-hidden="true" className="text-muted-foreground size-4" />
              <span className="text-muted-foreground">{t("hint", { mb: MAX_MB })}</span>
            </>
          ) : phase.kind === "uploading" ? (
            <>
              <Loader2 aria-hidden="true" className="size-4 animate-spin" />
              {t("uploading", { name: phase.name, percent: Math.round(phase.progress * 100) })}
            </>
          ) : phase.kind === "checking" ? (
            <>
              <Loader2 aria-hidden="true" className="size-4 animate-spin" />
              {t("checking", { name: phase.name })}
            </>
          ) : phase.kind === "done" ? (
            <>
              {phase.doc.scan_status === "pending" ? (
                <FileText aria-hidden="true" className="size-4" />
              ) : (
                <CheckCircle2 aria-hidden="true" className="text-success size-4" />
              )}
              {phase.doc.scan_status === "pending"
                ? t("stillChecking", { name: phase.doc.original_filename })
                : t("done", { name: phase.doc.original_filename })}
            </>
          ) : (
            <span className="text-destructive flex items-center gap-2" role="alert">
              <CircleAlert aria-hidden="true" className="size-4" />
              {phase.message}
            </span>
          )}
        </p>
      </div>
    </div>
  );
}
