"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useRef, useState } from "react";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

type Template = components["schemas"]["Template"];
type Rendered = components["schemas"]["Rendered"];
type Channel = "email" | "inapp";

const MANAGERS = ["org_admin", "hr_manager"];
const PLACEHOLDER = /\{\{\s*([a-z][a-z0-9_]*)\s*\}\}/g;
const base = "/hr/notification-templates";

export const templateKeys = {
  list: (orgId: string, channel: Channel) => ["notification-templates", orgId, channel] as const,
  history: (orgId: string, id: string) => ["notification-templates", orgId, "history", id] as const,
};

/** Placeholders used in ``text`` that this notification does not allow (shown before saving). */
export function unknownVariables(text: string, allowed: string[]): string[] {
  const used = [...text.matchAll(PLACEHOLDER)].map((m) => m[1]!);
  return [...new Set(used.filter((v) => !allowed.includes(v)))];
}

function errorText(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  const fields = Object.entries(err.fieldErrors()).map(([k, v]) => `${k}: ${v.join(" ")}`);
  return [err.message, ...fields].filter(Boolean).join(" ");
}

function Editor({
  template,
  channel,
  orgId,
  onDone,
}: {
  template: Template;
  channel: Channel;
  orgId: string;
  onDone: (notice: "saved" | "reverted") => void;
}) {
  const t = useTranslations("notifications.templates");
  const format = useFormatter();
  const client = useQueryClient();
  const o = { orgId };
  const [subject, setSubject] = useState(template.subject);
  const [body, setBody] = useState(template.body_md);
  const [preview, setPreview] = useState<Rendered | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reverting, setReverting] = useState(false);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const ids = { subject: useId(), body: useId(), vars: useId() };
  const history = useQuery({
    queryKey: templateKeys.history(orgId, template.id),
    queryFn: () => api.get<Template[]>(`${base}/${template.id}/history/`, o),
  });
  const refresh = () =>
    void client.invalidateQueries({ queryKey: ["notification-templates", orgId] });

  const doPreview = useMutation({
    mutationFn: () =>
      api.post<Rendered>(
        `${base}/${template.id}/preview/`,
        channel === "email" ? { subject, body_md: body } : { body_md: body },
        o,
      ),
    onSuccess: (r) => {
      setError(null);
      setPreview(r);
    },
    onError: (err) => setError(errorText(err, t("failed"))),
  });
  const save = useMutation({
    mutationFn: () =>
      api.post<Template>(
        `${base}/`,
        { key: template.key, channel, subject: channel === "email" ? subject : "", body_md: body },
        o,
      ),
    onSuccess: () => {
      setError(null);
      onDone("saved");
      refresh();
    },
    onError: (err) => setError(errorText(err, t("failed"))),
  });
  const revert = useMutation({
    mutationFn: () => api.post(`${base}/revert/`, { key: template.key, channel }, o),
    onSuccess: () => {
      setReverting(false);
      onDone("reverted");
      refresh();
    },
    onError: (err) => setError(errorText(err, t("failed"))),
  });

  const unknown = unknownVariables(`${subject}\n${body}`, template.allowed_variables);
  const dirty = subject !== template.subject || body !== template.body_md;

  const insert = (name: string) => {
    const el = bodyRef.current;
    const token = `{{ ${name} }}`;
    if (!el) return setBody((b) => b + token);
    const start = el.selectionStart ?? body.length;
    const end = el.selectionEnd ?? body.length;
    const next = body.slice(0, start) + token + body.slice(end);
    setBody(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + token.length, start + token.length);
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{template.description}</h2>
        <Badge variant={template.is_default ? "outline" : "secondary"}>
          {template.is_default ? t("default") : t("custom", { version: template.version })}
        </Badge>
      </div>
      {error ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        {channel === "email" ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={ids.subject}>{t("subject")}</Label>
            <Input
              id={ids.subject}
              value={subject}
              maxLength={200}
              className="h-10"
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
        ) : null}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={ids.body}>{channel === "email" ? t("body") : t("inappBody")}</Label>
          <textarea
            id={ids.body}
            ref={bodyRef}
            rows={channel === "email" ? 12 : 3}
            maxLength={20000}
            aria-describedby={ids.vars}
            className="border-input bg-background rounded-md border px-3 py-2 font-mono text-sm"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <p className="text-muted-foreground text-xs">
            {channel === "email" ? t("markdownHelp") : t("inappHelp")}
          </p>
        </div>
        <div id={ids.vars} className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">{t("variables")}</span>
          <div className="flex flex-wrap gap-1.5">
            {template.allowed_variables.map((v) => (
              <Button
                key={v}
                type="button"
                variant="outline"
                size="sm"
                className="font-mono text-xs"
                aria-label={t("insert", { name: v })}
                onClick={() => insert(v)}
              >
                {`{{ ${v} }}`}
              </Button>
            ))}
          </div>
          <p className="text-muted-foreground text-xs">{t("noSensitive")}</p>
        </div>
        {unknown.length ? (
          <p role="alert" className="text-destructive text-sm">
            {t("unknown", { names: unknown.join(", ") })}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button
            type="submit"
            className="min-h-10"
            disabled={!dirty || unknown.length > 0 || save.isPending}
          >
            {save.isPending ? t("saving") : t("save")}
          </Button>
          <Button
            type="button"
            variant="outline"
            className="min-h-10"
            disabled={unknown.length > 0 || doPreview.isPending}
            onClick={() => doPreview.mutate()}
          >
            {t("preview")}
          </Button>
          {!template.is_default ? (
            <Button
              type="button"
              variant="outline"
              className="min-h-10"
              onClick={() => setReverting(true)}
            >
              {t("revert")}
            </Button>
          ) : null}
        </div>
      </form>

      {preview ? (
        <section
          aria-labelledby="tpl-preview"
          className="flex flex-col gap-2 rounded-lg border p-3"
        >
          <h3 id="tpl-preview" className="font-medium">
            {t("previewTitle")}
          </h3>
          <p className="text-muted-foreground text-xs">{t("previewHelp")}</p>
          {channel === "email" ? (
            <>
              <p className="text-sm">
                <span className="text-muted-foreground">{t("subject")}: </span>
                {preview.subject}
              </p>
              {/* Sandboxed: no scripts, no navigation, nothing from the page can reach it. */}
              <iframe
                title={t("previewFrame")}
                sandbox=""
                srcDoc={preview.html}
                className="h-96 w-full rounded border bg-white"
              />
            </>
          ) : (
            <p className="rounded border p-2 text-sm">{preview.text.split("\n--\n")[0]}</p>
          )}
        </section>
      ) : null}

      <section aria-labelledby="tpl-history" className="flex flex-col gap-2">
        <h3 id="tpl-history" className="font-medium">
          {t("history")}
        </h3>
        {history.isPending ? (
          <p className="text-muted-foreground text-sm">{t("loading")}</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {(history.data ?? []).map((h) => (
              <li key={h.id} className="flex flex-wrap items-center gap-2">
                <span>
                  {h.is_default
                    ? t("defaultVersion", { version: h.version })
                    : t("customVersion", { version: h.version })}
                  {" · "}
                  {format.dateTime(new Date(h.created_at), {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </span>
                {h.id === template.id ? <Badge variant="outline">{t("inUse")}</Badge> : null}
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="h-auto p-0"
                  onClick={() => {
                    setSubject(h.subject);
                    setBody(h.body_md);
                    bodyRef.current?.focus();
                  }}
                >
                  {t("loadVersion")}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {reverting ? (
        <ConfirmDialog
          open
          onOpenChange={(open) => !open && setReverting(false)}
          title={t("revertTitle")}
          description={t("revertBody")}
          confirmLabel={t("revert")}
          pending={revert.isPending}
          onConfirm={() => revert.mutate()}
        />
      ) : null}
    </div>
  );
}

/** HR settings: notification templates (P05-T10). */
export function NotificationTemplateSettings() {
  const t = useTranslations("notifications.templates");
  const { orgId, role, isPending } = useJobsContext();
  const [channel, setChannel] = useState<Channel>("email");
  const [selected, setSelected] = useState<string | null>(null);
  const [notice, setNotice] = useState<"saved" | "reverted" | null>(null);
  const list = useQuery({
    queryKey: templateKeys.list(orgId ?? "", channel),
    queryFn: () => api.get<Template[]>(`${base}/`, { orgId: orgId!, query: { channel } }),
    enabled: !!orgId && !!role && MANAGERS.includes(role),
  });
  const pickId = useId();

  if (isPending) return <PageSkeleton />;
  if (!orgId || !role || !MANAGERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  if (list.isPending) return <PageSkeleton />;
  if (list.isError) return <ErrorState error={list.error} onRetry={() => list.refetch()} />;
  if (list.data.length === 0)
    return <EmptyState title={t("emptyTitle")} description={t("empty")} />;
  const current = list.data.find((x) => x.key === selected) ?? list.data[0]!;

  return (
    <section aria-labelledby="tpl-title" className="flex flex-col gap-4">
      <div>
        <h2 id="tpl-title" className="text-xl font-semibold">
          {t("title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("intro")}</p>
      </div>
      <div role="group" aria-label={t("channel")} className="flex gap-1.5">
        {(["email", "inapp"] as const).map((c) => (
          <Button
            key={c}
            type="button"
            size="sm"
            variant={channel === c ? "default" : "outline"}
            aria-pressed={channel === c}
            className="min-h-9"
            onClick={() => {
              setChannel(c);
              setNotice(null);
            }}
          >
            {t(`channels.${c}`)}
          </Button>
        ))}
      </div>
      <div className="flex flex-col gap-1.5 sm:max-w-md">
        <Label htmlFor={pickId}>{t("pick")}</Label>
        <select
          id={pickId}
          className="border-input bg-background h-10 rounded-md border px-3 text-sm"
          value={current.key}
          onChange={(e) => {
            setSelected(e.target.value);
            setNotice(null);
          }}
        >
          {list.data.map((x) => (
            <option key={x.key} value={x.key}>
              {x.description}
              {x.is_default ? "" : ` (${t("customShort")})`}
            </option>
          ))}
        </select>
      </div>
      <p role="status" className="text-success min-h-5 text-sm">
        {notice ? t(notice) : null}
      </p>
      <Editor
        key={`${current.id}:${channel}`}
        template={current}
        channel={channel}
        orgId={orgId}
        onDone={setNotice}
      />
    </section>
  );
}
