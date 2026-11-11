"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useId, useState } from "react";

import { StatusBadge } from "@/components/states/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FileUploader } from "@/features/documents/components/file-uploader";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

type Clarification = components["schemas"]["Clarification"];
type ThreadMessage = components["schemas"]["Message"];

const inputClass = "border-input bg-background rounded-md border px-3 py-2 text-sm";

export const conversationKeys = {
  clarifications: (id: string) => ["candidate", "applications", id, "clarifications"] as const,
  messages: (id: string) => ["candidate", "applications", id, "messages"] as const,
  actions: ["candidate", "actions"] as const,
};

function errorText(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  const fields = Object.values(err.fieldErrors()).flat();
  return [err.message, ...fields].filter(Boolean).join(" ");
}

/** One open clarification: a field per question, optional file where allowed (P05-T09). */
function AnswerForm({ applicationId, request }: { applicationId: string; request: Clarification }) {
  const t = useTranslations("candidate.clarifications");
  const client = useQueryClient();
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [files, setFiles] = useState<Record<string, { id: string; name: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const formId = useId();
  const answer = useMutation({
    mutationFn: () =>
      api.post<Clarification>(
        `/applications/${applicationId}/clarifications/${request.id}/answer/`,
        {
          answers: request.questions.map((q) => ({
            id: q.id,
            text: texts[q.id] ?? "",
            document_id: files[q.id]?.id ?? null,
          })),
        },
      ),
    onSuccess: () => {
      setError(null);
      void client.invalidateQueries({ queryKey: conversationKeys.clarifications(applicationId) });
      void client.invalidateQueries({ queryKey: conversationKeys.actions });
      void client.invalidateQueries({ queryKey: ["candidate", "applications", applicationId] });
    },
    onError: (err) => setError(errorText(err, t("failed"))),
  });
  const complete = request.questions.every((q) => (texts[q.id] ?? "").trim() || files[q.id]);

  return (
    <form
      aria-describedby={`${formId}-intro`}
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (complete) answer.mutate();
      }}
    >
      <p id={`${formId}-intro`} className="text-sm">
        {request.message || t("intro")}
      </p>
      {request.questions.map((q, i) => (
        <fieldset key={q.id} className="flex flex-col gap-2">
          <legend className="text-sm font-medium">
            {t("question", { n: i + 1 })}: {q.prompt}
          </legend>
          <textarea
            aria-label={t("answerLabel", { n: i + 1 })}
            rows={3}
            maxLength={5000}
            className={inputClass}
            value={texts[q.id] ?? ""}
            onChange={(e) => setTexts((cur) => ({ ...cur, [q.id]: e.target.value }))}
          />
          {q.allow_upload ? (
            files[q.id] ? (
              <p className="text-sm">
                {t("attached", { name: files[q.id]!.name })}{" "}
                <button
                  type="button"
                  className="min-h-6 underline"
                  onClick={() =>
                    setFiles((cur) => {
                      const next = { ...cur };
                      delete next[q.id];
                      return next;
                    })
                  }
                >
                  {t("removeFile")}
                </button>
              </p>
            ) : (
              <FileUploader
                purpose="supporting"
                label={t("upload")}
                onUploaded={(doc) =>
                  setFiles((cur) => ({
                    ...cur,
                    [q.id]: { id: doc.id, name: doc.original_filename },
                  }))
                }
              />
            )
          ) : null}
        </fieldset>
      ))}
      {error ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <Button
        type="submit"
        className="min-h-11 self-start"
        disabled={!complete || answer.isPending}
      >
        {answer.isPending ? t("sending") : t("send")}
      </Button>
    </form>
  );
}

export function CandidateClarifications({ applicationId }: { applicationId: string }) {
  const t = useTranslations("candidate.clarifications");
  const format = useFormatter();
  const list = useQuery({
    queryKey: conversationKeys.clarifications(applicationId),
    queryFn: () => api.get<Clarification[]>(`/applications/${applicationId}/clarifications/`),
  });
  const rows = list.data ?? [];
  if (rows.length === 0) return null;
  return (
    <section
      id="clarifications"
      aria-labelledby="clarifications-title"
      className="flex flex-col gap-4 rounded-lg border p-4"
    >
      <h2 id="clarifications-title" className="text-lg font-semibold">
        {t("title")}
      </h2>
      {rows.map((c) => (
        <article key={c.id} className="flex flex-col gap-3 rounded-md border p-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <StatusBadge status={`clarification_${c.status}`} />
            <span className="text-muted-foreground">
              {t("due", {
                date: format.dateTime(new Date(c.due_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                }),
              })}
            </span>
          </div>
          {c.status === "open" ? (
            <AnswerForm applicationId={applicationId} request={c} />
          ) : (
            <ol className="list-decimal space-y-2 pl-5 text-sm">
              {c.questions.map((q) => {
                const a = c.answers.find((x) => x.id === q.id);
                return (
                  <li key={q.id}>
                    <p className="font-medium">{q.prompt}</p>
                    {a?.text ? <p className="whitespace-pre-line">{a.text}</p> : null}
                    {a?.document_id ? (
                      <p className="text-muted-foreground">{t("fileSent")}</p>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          )}
          {c.status === "expired" ? <p className="text-sm">{t("expired")}</p> : null}
        </article>
      ))}
    </section>
  );
}

export function CandidateMessages({
  applicationId,
  canWrite,
}: {
  applicationId: string;
  canWrite: boolean;
}) {
  const t = useTranslations("candidate.messages");
  const format = useFormatter();
  const client = useQueryClient();
  const messages = useQuery({
    queryKey: conversationKeys.messages(applicationId),
    queryFn: () => api.get<ThreadMessage[]>(`/applications/${applicationId}/messages/`),
    refetchInterval: 30_000,
  });
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const send = useMutation({
    mutationFn: () =>
      api.post<ThreadMessage>(`/applications/${applicationId}/messages/`, {
        body,
        attachment_ids: files.map((f) => f.id),
      }),
    onSuccess: () => {
      setBody("");
      setFiles([]);
      setError(null);
      void client.invalidateQueries({ queryKey: conversationKeys.messages(applicationId) });
    },
    onError: (err) => setError(errorText(err, t("failed"))),
  });
  // Reading the thread marks employer messages read; refresh the dashboard "to do" list.
  const loadedAt = messages.dataUpdatedAt;
  useEffect(() => {
    if (loadedAt) void client.invalidateQueries({ queryKey: conversationKeys.actions });
  }, [loadedAt, client]);

  return (
    <section
      id="messages"
      aria-labelledby="messages-title"
      className="flex flex-col gap-3 rounded-lg border p-4"
    >
      <h2 id="messages-title" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-xs">{t("privacy")}</p>
      {messages.isPending ? (
        <p className="text-muted-foreground text-sm">{t("loading")}</p>
      ) : (messages.data ?? []).length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("empty")}</p>
      ) : (
        <ol className="flex flex-col gap-2" aria-live="polite">
          {(messages.data ?? []).map((m) => (
            <li
              key={m.id}
              className={`max-w-[85%] rounded-lg border p-2 text-sm ${m.mine ? "bg-primary/5 self-end" : "bg-muted/40 self-start"}`}
            >
              <p className="text-muted-foreground mb-1 text-xs">
                {m.mine ? t("you") : m.sender_name} ·{" "}
                {format.dateTime(new Date(m.created_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
              </p>
              <p className="whitespace-pre-line">{m.body}</p>
              {m.attachment_document_ids.map((d) => (
                <a
                  key={d}
                  className="mt-1 block text-xs underline"
                  href={`/api/v1/documents/${d}/download/`}
                >
                  {t("attachment")}
                </a>
              ))}
            </li>
          ))}
        </ol>
      )}
      {canWrite ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (body.trim()) send.mutate();
          }}
        >
          <label htmlFor={id} className="text-sm font-medium">
            {t("write")}
          </label>
          <textarea
            id={id}
            rows={3}
            maxLength={5000}
            className={inputClass}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          {files.length ? (
            <ul className="text-sm">
              {files.map((f) => (
                <li key={f.id}>
                  {t("attached", { name: f.name })}{" "}
                  <button
                    type="button"
                    className="min-h-6 underline"
                    onClick={() => setFiles((cur) => cur.filter((x) => x.id !== f.id))}
                  >
                    {t("removeFile")}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {files.length < 3 ? (
            <FileUploader
              purpose="message_attachment"
              label={t("attach")}
              onUploaded={(doc) =>
                setFiles((cur) => [...cur, { id: doc.id, name: doc.original_filename }])
              }
            />
          ) : null}
          {error ? (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          ) : null}
          <Button
            type="submit"
            className="min-h-11 self-start"
            disabled={!body.trim() || send.isPending}
          >
            {t("send")}
          </Button>
        </form>
      ) : (
        <p className="text-muted-foreground text-sm">{t("closed")}</p>
      )}
    </section>
  );
}
