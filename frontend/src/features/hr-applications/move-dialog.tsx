"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError } from "@/lib/api-client";

import { atsApi, atsKeys, reasonListFor, useHRApplication } from "./api";

const selectClass =
  "border-input bg-background h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none";

/**
 * Status change with server validation. ``target`` is pre-selected when the move comes from a
 * drag; otherwise the person picks from the moves they are allowed to make. Mount it only while
 * open so every opening starts from a clean form.
 */
export function MoveDialog({
  applicationId,
  target,
  open,
  onOpenChange,
  onMoved,
}: {
  applicationId: string;
  target?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onMoved?: () => void;
}) {
  const t = useTranslations("hrApplications.move");
  const ts = useTranslations("status");
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const app = useHRApplication(applicationId);
  const [to, setTo] = useState(target ?? "");
  const [code, setCode] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ids = { to: useId(), code: useId(), text: useId() };

  const from = app.data?.status ?? "";
  const allowed = app.data?.allowed_transitions ?? [];
  const list = to && from ? reasonListFor(from, to) : null;
  const reasons = useQuery({
    queryKey: atsKeys.reasons(orgId ?? "", list ?? ""),
    queryFn: () => atsApi(orgId!).reasons(list!),
    enabled: open && !!orgId && !!list,
  });
  const label = (s: string) => (ts.has(s) ? ts(s) : s.replaceAll("_", " "));

  const move = useMutation({
    mutationFn: () =>
      atsApi(orgId!).transition(applicationId, {
        to_status: to,
        reason_code: code,
        reason_text: text,
        lock_version: app.data?.lock_version,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["hr-applications"] });
      onMoved?.();
      onOpenChange(false);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "conflict.invalid_transition") {
        const options = (err.details.allowed as string[] | undefined) ?? [];
        setError(
          t("notAllowed", {
            from: label(from),
            to: label(to),
            options: options.map(label).join(", ") || t("none"),
          }),
        );
      } else if (err instanceof ApiError && err.code === "conflict.stale_version") {
        void app.refetch();
        setError(t("stale"));
      } else if (err instanceof ApiError && err.status === 403) {
        setError(t("forbidden"));
      } else if (err instanceof ApiError) {
        const field = err.fieldErrors();
        setError([err.message, ...Object.values(field).flat()].join(" "));
      } else {
        setError(t("failed"));
      }
    },
  });

  const blocked = !!to && !!from && !allowed.includes(to);
  const needsText = code === "other";
  const ready =
    !!app.data && !!to && !blocked && (!list || !!code) && (!needsText || text.trim().length >= 5);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>
            {app.data ? t("from", { status: label(from) }) : t("loading")}
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) move.mutate();
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={ids.to}>{t("to")}</Label>
            <select
              id={ids.to}
              className={selectClass}
              value={to}
              onChange={(e) => {
                setTo(e.target.value);
                setCode("");
                setError(null);
              }}
            >
              <option value="">{t("choose")}</option>
              {(target && !allowed.includes(target) ? [target, ...allowed] : allowed).map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </div>
          {blocked && app.data ? (
            <Alert variant="destructive" role="alert">
              <AlertDescription>
                {t("notAllowed", {
                  from: label(from),
                  to: label(to),
                  options: allowed.map(label).join(", ") || t("none"),
                })}
              </AlertDescription>
            </Alert>
          ) : null}
          {list && !blocked ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={ids.code}>
                {t("reason")}{" "}
                <span className="text-muted-foreground font-normal">{t("required")}</span>
              </Label>
              <select
                id={ids.code}
                className={selectClass}
                value={code}
                aria-required="true"
                onChange={(e) => setCode(e.target.value)}
              >
                <option value="">{t("chooseReason")}</option>
                {(reasons.data ?? []).map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          {to && !blocked ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={ids.text}>
                {t("note")}{" "}
                <span className="text-muted-foreground font-normal">
                  {needsText ? t("required") : t("optional")}
                </span>
              </Label>
              <textarea
                id={ids.text}
                rows={3}
                maxLength={2000}
                className="border-input bg-background rounded-md border px-3 py-2 text-sm"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              {to === "shortlisted" || to === "not_selected" ? (
                <p className="text-muted-foreground text-xs">{t("delayNotice")}</p>
              ) : null}
            </div>
          ) : null}
          {error ? (
            <Alert variant="destructive" role="alert">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("cancel")}
            </Button>
            <Button type="submit" disabled={!ready || move.isPending}>
              {move.isPending ? t("saving") : t("confirm")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
