"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";

import { StatusBadge } from "@/components/states/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError } from "@/lib/api-client";

import { atsApi, atsKeys, hrApplicationKeys, type HRApplicationDetail } from "./api";
import { MoveDialog } from "./move-dialog";

const inputClass = "border-input bg-background rounded-md border px-3 py-2 text-sm";
const DECIDERS = ["org_admin", "hr_manager"];
const EDITORS = ["org_admin", "hr_manager", "recruiter"];

function errorText(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  const fields = Object.values(err.fieldErrors()).flat();
  return [err.message, ...fields].filter(Boolean).join(" ");
}

function useApi() {
  const { orgId, role } = useJobsContext();
  return { orgId: orgId ?? "", role: role ?? "", api: atsApi(orgId ?? "") };
}

function useTeam(jobId: string) {
  const { orgId, api } = useApi();
  return useQuery({
    queryKey: atsKeys.team(orgId, jobId),
    queryFn: () => api.team(jobId),
    enabled: !!orgId,
  });
}

// ------------------------------------------------------------------------------ actions
export function ActionsPanel({ app }: { app: HRApplicationDetail }) {
  const t = useTranslations("hrApplications.actions");
  const { orgId, role, api } = useApi();
  const client = useQueryClient();
  const team = useTeam(app.job.id);
  const [moving, setMoving] = useState(false);
  const [tagInput, setTagInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ids = { assign: useId(), tags: useId() };
  const refresh = (data: HRApplicationDetail) => {
    client.setQueryData(hrApplicationKeys.detail(orgId, app.id), data);
    void client.invalidateQueries({ queryKey: ["hr-applications", orgId, "job"] });
  };
  const tags = useMutation({
    mutationFn: (next: string[]) => api.setTags(app.id, next),
    onSuccess: (data) => {
      setTagInput("");
      setError(null);
      refresh(data);
    },
    onError: (err) => setError(errorText(err, t("failed"))),
  });
  const assign = useMutation({
    mutationFn: (userId: string | null) => api.assign(app.id, userId),
    onSuccess: (data) => {
      setError(null);
      refresh(data);
    },
    onError: (err) => setError(errorText(err, t("failed"))),
  });
  const recruiters = (team.data ?? []).filter((m) => ["recruiter"].includes(m.role_on_job));
  const canEdit = EDITORS.includes(role);

  return (
    <section aria-labelledby="hr-actions" className="flex flex-col gap-3 rounded-lg border p-4">
      <h2 id="hr-actions" className="text-lg font-semibold">
        {t("title")}
      </h2>
      {error ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          className="min-h-10"
          disabled={!canEdit || app.allowed_transitions.length === 0}
          onClick={() => setMoving(true)}
        >
          {t("changeStatus")}
        </Button>
        {app.allowed_transitions.length === 0 ? (
          <span className="text-muted-foreground text-sm">{t("noMoves")}</span>
        ) : null}
      </div>
      {DECIDERS.includes(role) ? (
        <div className="flex flex-col gap-1.5 sm:max-w-sm">
          <Label htmlFor={ids.assign}>{t("assign")}</Label>
          <select
            id={ids.assign}
            className={`${inputClass} h-10`}
            value={app.assigned_recruiter ?? ""}
            disabled={assign.isPending}
            onChange={(e) => assign.mutate(e.target.value || null)}
          >
            <option value="">{t("unassigned")}</option>
            {recruiters.map((m) => (
              <option key={m.id} value={m.user_id}>
                {m.user_name}
              </option>
            ))}
          </select>
        </div>
      ) : app.assigned_recruiter ? (
        <p className="text-sm">
          {t("assignedTo", {
            name: team.data?.find((m) => m.user_id === app.assigned_recruiter)?.user_name ?? "—",
          })}
        </p>
      ) : null}
      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">{t("tags")}</span>
        <ul className="flex flex-wrap gap-1.5" aria-label={t("tags")}>
          {app.tags.length === 0 ? (
            <li className="text-muted-foreground text-sm">{t("noTags")}</li>
          ) : null}
          {app.tags.map((tag) => (
            <li key={tag}>
              <Badge variant="outline" className="gap-1">
                {tag}
                {canEdit ? (
                  <button
                    type="button"
                    className="min-h-6 px-1"
                    aria-label={t("removeTag", { tag })}
                    onClick={() => tags.mutate(app.tags.filter((x) => x !== tag))}
                  >
                    ×
                  </button>
                ) : null}
              </Badge>
            </li>
          ))}
        </ul>
        {canEdit ? (
          <form
            className="flex gap-2 sm:max-w-sm"
            onSubmit={(e) => {
              e.preventDefault();
              if (tagInput.trim()) tags.mutate([...app.tags, tagInput]);
            }}
          >
            <Label htmlFor={ids.tags} className="sr-only">
              {t("addTag")}
            </Label>
            <Input
              id={ids.tags}
              value={tagInput}
              maxLength={40}
              placeholder={t("tagPlaceholder")}
              onChange={(e) => setTagInput(e.target.value)}
              className="h-10"
            />
            <Button type="submit" variant="outline" className="min-h-10" disabled={tags.isPending}>
              {t("addTag")}
            </Button>
          </form>
        ) : null}
      </div>
      {moving ? <MoveDialog applicationId={app.id} open onOpenChange={setMoving} /> : null}
    </section>
  );
}

// -------------------------------------------------------------------------------- notes
export function NotesPanel({ app }: { app: HRApplicationDetail }) {
  const t = useTranslations("hrApplications.notes");
  const format = useFormatter();
  const { orgId, api } = useApi();
  const client = useQueryClient();
  const team = useTeam(app.job.id);
  const notes = useQuery({
    queryKey: atsKeys.notes(orgId, app.id),
    queryFn: () => api.notes(app.id),
    enabled: !!orgId,
  });
  const [body, setBody] = useState("");
  const [mentions, setMentions] = useState<string[]>([]);
  const [priv, setPriv] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ids = { body: useId(), priv: useId() };
  const add = useMutation({
    mutationFn: () =>
      api.addNote(app.id, {
        body,
        mentions: priv ? [] : mentions,
        visibility: priv ? "private" : "team",
      }),
    onSuccess: () => {
      setBody("");
      setMentions([]);
      setPriv(false);
      setError(null);
      void client.invalidateQueries({ queryKey: atsKeys.notes(orgId, app.id) });
    },
    onError: (err) => setError(errorText(err, t("failed"))),
  });
  const colleagues = (team.data ?? []).filter(
    (m, i, all) => all.findIndex((x) => x.user_id === m.user_id) === i,
  );

  return (
    <section
      id="notes"
      aria-labelledby="hr-notes"
      className="flex flex-col gap-3 rounded-lg border p-4"
    >
      <h2 id="hr-notes" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className="text-muted-foreground text-xs">{t("internal")}</p>
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (body.trim()) add.mutate();
        }}
      >
        <Label htmlFor={ids.body}>{t("add")}</Label>
        <textarea
          id={ids.body}
          rows={3}
          maxLength={5000}
          className={inputClass}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        {!priv && colleagues.length ? (
          <fieldset className="flex flex-col gap-1">
            <legend className="text-sm font-medium">{t("mention")}</legend>
            <div className="flex flex-wrap gap-3">
              {colleagues.map((m) => (
                <label key={m.user_id} className="flex min-h-6 items-center gap-1.5 text-sm">
                  <input
                    type="checkbox"
                    className="size-4"
                    checked={mentions.includes(m.user_id)}
                    onChange={(e) =>
                      setMentions((cur) =>
                        e.target.checked ? [...cur, m.user_id] : cur.filter((x) => x !== m.user_id),
                      )
                    }
                  />
                  {m.user_name}
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}
        <label htmlFor={ids.priv} className="flex min-h-6 items-center gap-1.5 text-sm">
          <input
            id={ids.priv}
            type="checkbox"
            className="size-4"
            checked={priv}
            onChange={(e) => setPriv(e.target.checked)}
          />
          {t("private")}
        </label>
        {error ? (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        ) : null}
        <Button
          type="submit"
          className="min-h-10 self-start"
          disabled={!body.trim() || add.isPending}
        >
          {t("save")}
        </Button>
      </form>
      {notes.isPending ? (
        <p className="text-muted-foreground text-sm">{t("loading")}</p>
      ) : (notes.data ?? []).length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {(notes.data ?? []).map((n) => (
            <li key={n.id} className="border-l-2 pl-3 text-sm">
              <p className="whitespace-pre-line">{n.body}</p>
              <p className="text-muted-foreground mt-1 text-xs">
                {n.author_name} ·{" "}
                {format.dateTime(new Date(n.created_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
                {n.visibility === "private" ? ` · ${t("privateLabel")}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ----------------------------------------------------------------------- clarifications
function inDays(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  d.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function ClarificationsPanel({ app }: { app: HRApplicationDetail }) {
  const t = useTranslations("hrApplications.clarifications");
  const format = useFormatter();
  const { orgId, role, api } = useApi();
  const client = useQueryClient();
  const list = useQuery({
    queryKey: atsKeys.clarifications(orgId, app.id),
    queryFn: () => api.clarifications(app.id),
    enabled: !!orgId,
  });
  const templates = useQuery({
    queryKey: atsKeys.templates(orgId),
    queryFn: () => api.templates(),
    enabled: !!orgId,
  });
  const [questions, setQuestions] = useState<{ prompt: string; allow_upload: boolean }[]>([
    { prompt: "", allow_upload: false },
  ]);
  const [message, setMessage] = useState("");
  const [due, setDue] = useState(() => inDays(3));
  const [error, setError] = useState<string | null>(null);
  const ids = { template: useId(), message: useId(), due: useId() };
  const refresh = () => {
    void client.invalidateQueries({ queryKey: atsKeys.clarifications(orgId, app.id) });
    void client.invalidateQueries({ queryKey: hrApplicationKeys.detail(orgId, app.id) });
  };
  const ask = useMutation({
    mutationFn: () =>
      api.askClarification(app.id, {
        questions: questions.filter((q) => q.prompt.trim()),
        due_at: new Date(due).toISOString(),
        message,
      }),
    onSuccess: () => {
      setQuestions([{ prompt: "", allow_upload: false }]);
      setMessage("");
      setError(null);
      refresh();
    },
    onError: (err) => setError(errorText(err, t("failed"))),
  });
  const cancel = useMutation({
    mutationFn: (cid: string) => api.cancelClarification(app.id, cid),
    onSuccess: refresh,
    onError: (err) => setError(errorText(err, t("failed"))),
  });
  const open = (list.data ?? []).find((c) => c.status === "open");
  const canAsk =
    EDITORS.includes(role) && !open && ["under_review", "processing"].includes(app.status);

  return (
    <section
      id="clarifications"
      aria-labelledby="hr-clarifications"
      className="flex flex-col gap-3 rounded-lg border p-4"
    >
      <h2 id="hr-clarifications" className="text-lg font-semibold">
        {t("title")}
      </h2>
      {error ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {(list.data ?? []).map((c) => (
        <article key={c.id} className="flex flex-col gap-2 rounded-md border p-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <StatusBadge status={`clarification_${c.status}`} />
            <span className="text-muted-foreground text-xs">
              {t("due", {
                date: format.dateTime(new Date(c.due_at), {
                  dateStyle: "medium",
                  timeStyle: "short",
                }),
              })}
            </span>
          </div>
          <ol className="list-decimal space-y-2 pl-5">
            {c.questions.map((q) => {
              const a = c.answers.find((x) => x.id === q.id);
              return (
                <li key={q.id}>
                  <p className="font-medium">{q.prompt}</p>
                  {a ? (
                    <p className="whitespace-pre-line">
                      {a.text || null}
                      {a.document_id ? (
                        <a
                          className="ml-2 underline"
                          href={`/api/v1/documents/${a.document_id}/download/`}
                        >
                          {t("attachment")}
                        </a>
                      ) : null}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ol>
          {c.status === "answered" ? (
            <p className="text-muted-foreground text-xs">{t("candidateReported")}</p>
          ) : null}
          {(c.status === "open" || c.status === "expired") && EDITORS.includes(role) ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="self-start"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate(c.id)}
            >
              {t("cancel")}
            </Button>
          ) : null}
        </article>
      ))}
      {canAsk ? (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            ask.mutate();
          }}
        >
          <h3 className="font-medium">{t("ask")}</h3>
          <div className="flex flex-col gap-1.5 sm:max-w-md">
            <Label htmlFor={ids.template}>{t("template")}</Label>
            <select
              id={ids.template}
              className={`${inputClass} h-10`}
              value=""
              onChange={(e) => {
                const tpl = templates.data?.find((x) => x.key === e.target.value);
                if (!tpl) return;
                setQuestions((qs) => {
                  const kept = qs.filter((q) => q.prompt.trim());
                  return [...kept, { prompt: tpl.prompt, allow_upload: tpl.allow_upload }].slice(
                    0,
                    5,
                  );
                });
              }}
            >
              <option value="">{t("chooseTemplate")}</option>
              {(templates.data ?? []).map((tpl) => (
                <option key={tpl.key} value={tpl.key}>
                  {tpl.prompt}
                </option>
              ))}
            </select>
          </div>
          {questions.map((q, i) => (
            <fieldset key={i} className="flex flex-col gap-1.5">
              <legend className="text-sm font-medium">{t("question", { n: i + 1 })}</legend>
              <textarea
                aria-label={t("question", { n: i + 1 })}
                rows={2}
                maxLength={1000}
                className={inputClass}
                value={q.prompt}
                onChange={(e) =>
                  setQuestions((qs) =>
                    qs.map((x, j) => (j === i ? { ...x, prompt: e.target.value } : x)),
                  )
                }
              />
              <label className="flex min-h-6 items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  className="size-4"
                  checked={q.allow_upload}
                  onChange={(e) =>
                    setQuestions((qs) =>
                      qs.map((x, j) => (j === i ? { ...x, allow_upload: e.target.checked } : x)),
                    )
                  }
                />
                {t("allowUpload")}
              </label>
            </fieldset>
          ))}
          {questions.length < 5 ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="self-start"
              onClick={() => setQuestions((qs) => [...qs, { prompt: "", allow_upload: false }])}
            >
              {t("addQuestion")}
            </Button>
          ) : null}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={ids.message}>{t("message")}</Label>
            <textarea
              id={ids.message}
              rows={2}
              maxLength={2000}
              className={inputClass}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5 sm:max-w-xs">
            <Label htmlFor={ids.due}>{t("dueLabel")}</Label>
            <Input
              id={ids.due}
              type="datetime-local"
              className="h-10"
              value={due}
              onChange={(e) => setDue(e.target.value)}
            />
          </div>
          <p className="text-muted-foreground text-xs">{t("privacy")}</p>
          <Button
            type="submit"
            className="min-h-10 self-start"
            disabled={!questions.some((q) => q.prompt.trim()) || ask.isPending}
          >
            {t("send")}
          </Button>
        </form>
      ) : !open && (list.data ?? []).length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("notNow")}</p>
      ) : null}
    </section>
  );
}

// ----------------------------------------------------------------------------- messages
export function MessagesPanel({ app }: { app: HRApplicationDetail }) {
  const t = useTranslations("hrApplications.messages");
  const format = useFormatter();
  const { orgId, api } = useApi();
  const client = useQueryClient();
  const messages = useQuery({
    queryKey: atsKeys.messages(orgId, app.id),
    queryFn: () => api.messages(app.id),
    enabled: !!orgId,
    refetchInterval: 30_000,
  });
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const send = useMutation({
    mutationFn: () => api.sendMessage(app.id, body),
    onSuccess: () => {
      setBody("");
      setError(null);
      void client.invalidateQueries({ queryKey: atsKeys.messages(orgId, app.id) });
    },
    onError: (err) => setError(errorText(err, t("failed"))),
  });
  const closed = app.status === "withdrawn";

  return (
    <section
      id="messages"
      aria-labelledby="hr-messages"
      className="flex flex-col gap-3 rounded-lg border p-4"
    >
      <h2 id="hr-messages" className="text-lg font-semibold">
        {t("title")}
      </h2>
      {messages.isPending ? (
        <p className="text-muted-foreground text-sm">{t("loading")}</p>
      ) : (messages.data ?? []).length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("empty")}</p>
      ) : (
        <ol className="flex flex-col gap-2" aria-live="polite">
          {(messages.data ?? []).map((m) => (
            <li
              key={m.id}
              className={`max-w-[85%] rounded-lg border p-2 text-sm ${
                m.mine ? "bg-primary/5 self-end" : "bg-muted/40 self-start"
              }`}
            >
              <p className="text-muted-foreground mb-1 text-xs">
                {m.sender_role === "candidate" ? t("candidate") : m.sender_name} ·{" "}
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
      {closed ? (
        <p className="text-muted-foreground text-sm">{t("closed")}</p>
      ) : (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (body.trim()) send.mutate();
          }}
        >
          <Label htmlFor={id}>{t("write")}</Label>
          <textarea
            id={id}
            rows={3}
            maxLength={5000}
            className={inputClass}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          {error ? (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          ) : null}
          <Button
            type="submit"
            className="min-h-10 self-start"
            disabled={!body.trim() || send.isPending}
          >
            {t("send")}
          </Button>
        </form>
      )}
    </section>
  );
}
