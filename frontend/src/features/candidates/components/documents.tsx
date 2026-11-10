"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Star, Trash2 } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { EmptyState, ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { documentsApi } from "@/features/documents/api";
import { FileUploader } from "@/features/documents/components/file-uploader";
import { ApiError, api } from "@/lib/api-client";

import { candidateKeys, useResumes, type Resume } from "../hooks";

export function ScanChip({ status }: { status: string }) {
  const t = useTranslations("candidate.documents.scan");
  const variant =
    status === "clean" || status === "skipped"
      ? "secondary"
      : status === "pending"
        ? "outline"
        : "destructive";
  const key = status === "rejected" ? "notAccepted" : status;
  return <Badge variant={variant}>{t.has(key) ? t(key) : status}</Badge>;
}

export function CandidateDocuments() {
  const t = useTranslations("candidate.documents");
  const format = useFormatter();
  const client = useQueryClient();
  const resumes = useResumes();
  const [removing, setRemoving] = useState<Resume | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => {
    void client.invalidateQueries({ queryKey: candidateKeys.resumes });
    void client.invalidateQueries({ queryKey: candidateKeys.profile });
  };
  const setDefault = useMutation({
    mutationFn: (id: string) => api.post(`/candidate/resumes/${id}/set-default/`),
    onSuccess: refresh,
    onError: (err) => setError(err instanceof ApiError ? err.message : t("failed")),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/candidate/resumes/${id}/`),
    onSuccess: () => {
      setRemoving(null);
      refresh();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : t("failed")),
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <FileUploader
        purpose="cv"
        label={t("upload")}
        description={t("uploadHelp")}
        onUploaded={refresh}
      />
      {error ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {resumes.isPending ? (
        <PageSkeleton rows={3} />
      ) : resumes.isError ? (
        <ErrorState error={resumes.error} onRetry={() => resumes.refetch()} />
      ) : resumes.data.length === 0 ? (
        <EmptyState title={t("emptyTitle")} description={t("empty")} />
      ) : (
        <ul className="flex flex-col gap-2" aria-label={t("listLabel")}>
          {resumes.data.map((r) => (
            <li
              key={r.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"
            >
              <div className="flex flex-col gap-1">
                <span className="font-medium">
                  {r.original_filename}
                  {r.is_default ? (
                    <Badge className="ml-2" variant="secondary">
                      {t("default")}
                    </Badge>
                  ) : null}
                </span>
                <span className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
                  <ScanChip status={r.scan_status} />
                  {format.dateTime(new Date(r.created_at), { dateStyle: "medium" })}
                  {r.page_count ? ` · ${t("pages", { count: r.page_count })}` : ""}
                  {` · ${Math.max(1, Math.round(r.size_bytes / 1024))} KB`}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {r.scan_status === "clean" || r.scan_status === "skipped" ? (
                  <Button asChild size="sm" variant="outline">
                    <a href={documentsApi.downloadUrl(r.id)}>
                      <Download aria-hidden="true" />
                      {t("download", { name: r.original_filename })}
                    </a>
                  </Button>
                ) : null}
                {!r.is_default && r.scan_status !== "infected" && r.scan_status !== "rejected" ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setDefault.mutate(r.id)}
                    disabled={setDefault.isPending}
                  >
                    <Star aria-hidden="true" />
                    {t("makeDefault")}
                  </Button>
                ) : null}
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={t("remove", { name: r.original_filename })}
                  onClick={() => setRemoving(r)}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {removing ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setRemoving(null)}
          title={t("removeTitle")}
          description={t("removeBody", { name: removing.original_filename })}
          confirmLabel={t("removeConfirm")}
          destructive
          pending={remove.isPending}
          error={error}
          onConfirm={() => remove.mutate(removing.id)}
        />
      ) : null}
    </div>
  );
}
