"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { ErrorSummary, TextField, useErrorText } from "@/components/forms/form-field";
import { ErrorState } from "@/components/states/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { applyServerErrors } from "@/features/auth/form-errors";
import { api, ApiError, newIdempotencyKey } from "@/lib/api-client";
import type { components } from "@/types/api";

export type CandidateInterview = components["schemas"]["CandidateInterview"];
export type CandidateOffer = components["schemas"]["CandidateOffer"];

export const candidateHiringKeys = {
  interviews: (appId: string) => ["candidate", "applications", appId, "interviews"] as const,
  offers: (appId: string) => ["candidate", "applications", appId, "offers"] as const,
};

/** Offer states in which the candidate can still answer. */
export function canRespond(offer: Pick<CandidateOffer, "status" | "expires_at">, now = new Date()) {
  return offer.status === "issued" && new Date(offer.expires_at).getTime() > now.getTime();
}

/** Slots the candidate may still pick: not booked and not in the past. */
export function openSlots(interview: CandidateInterview, now = new Date()) {
  if (interview.status !== "proposed") return [];
  return interview.slots
    .filter((s) => !s.booked && new Date(s.starts_at).getTime() > now.getTime())
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
}

function useWhen() {
  const format = useFormatter();
  return (iso: string, timeZone?: string) =>
    format.dateTime(new Date(iso), {
      dateStyle: "full",
      timeStyle: "short",
      ...(timeZone ? { timeZone } : {}),
    });
}

// ---------------------------------------------------------------------------------------------
// Interviews

export function CandidateInterviews({ applicationId }: { applicationId: string }) {
  const t = useTranslations("candidateHiring.interviews");
  const query = useQuery({
    queryKey: candidateHiringKeys.interviews(applicationId),
    queryFn: () => api.get<CandidateInterview[]>(`/applications/${applicationId}/interviews/`),
  });
  if (query.isPending || (query.data && query.data.length === 0)) return null;
  return (
    <Card id="interviews">
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {query.isError ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} />
        ) : (
          query.data.map((iv) => (
            <InterviewItem key={iv.id} interview={iv} applicationId={applicationId} />
          ))
        )}
      </CardContent>
    </Card>
  );
}

function InterviewItem({
  interview: iv,
  applicationId,
}: {
  interview: CandidateInterview;
  applicationId: string;
}) {
  const t = useTranslations("candidateHiring.interviews");
  const when = useWhen();
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const book = useMutation({
    mutationFn: (slotId: string) =>
      api.post<CandidateInterview>(
        `/interviews/${iv.id}/book/`,
        { slot_id: slotId },
        { idempotencyKey: newIdempotencyKey() },
      ),
    onSuccess: async () => {
      setError(null);
      // Refreshes the interview list and the application timeline together.
      await client.invalidateQueries({ queryKey: ["candidate", "applications", applicationId] });
    },
    onError: async (err) => {
      setError(err instanceof ApiError ? err.message : t("failed"));
      // Someone else may have taken the slot: show the current choices.
      await client.invalidateQueries({ queryKey: candidateHiringKeys.interviews(applicationId) });
    },
  });
  const slots = openSlots(iv);
  const status = t.has(`status.${iv.status}`) ? t(`status.${iv.status}`) : iv.status;
  const mode = t.has(`mode.${iv.mode}`) ? t(`mode.${iv.mode}`) : iv.mode;
  return (
    <section className="flex flex-col gap-2 border-l-2 pl-4" aria-label={iv.stage || t("title")}>
      <h3 className="font-medium">
        {iv.stage || t("title")} · <span className="text-muted-foreground">{status}</span>
      </h3>
      <p className="text-sm">
        {mode} · {t("duration", { minutes: iv.duration_minutes })}
      </p>
      {iv.starts_at && iv.status !== "cancelled" ? (
        <p className="text-sm font-medium">{when(iv.starts_at, iv.timezone)}</p>
      ) : null}
      {iv.status === "scheduled" && iv.location ? (
        <p className="text-sm">{t("where", { location: iv.location })}</p>
      ) : null}
      {iv.status === "scheduled" && iv.video_link ? (
        <p className="text-sm">
          <a className="underline" href={iv.video_link} target="_blank" rel="noopener noreferrer">
            {t("join")}
          </a>
        </p>
      ) : null}
      {iv.instructions ? (
        <p className="text-muted-foreground text-sm whitespace-pre-line">{iv.instructions}</p>
      ) : null}
      {iv.status_reason && ["cancelled", "scheduled"].includes(iv.status) ? (
        <p className="text-muted-foreground text-sm">{t("note", { note: iv.status_reason })}</p>
      ) : null}

      {iv.status === "proposed" ? (
        slots.length > 0 ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium">{t("chooseTime")}</legend>
            <ul className="flex flex-col gap-2">
              {slots.map((s) => (
                <li key={s.id}>
                  <Button
                    variant="outline"
                    className="h-auto min-h-10 w-full justify-start text-left whitespace-normal"
                    disabled={book.isPending}
                    onClick={() => book.mutate(s.id)}
                  >
                    {when(s.starts_at, iv.timezone)}
                  </Button>
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground text-xs">{t("timezone", { zone: iv.timezone })}</p>
          </fieldset>
        ) : (
          <p className="text-sm">{t("noSlots")}</p>
        )
      ) : null}

      {iv.status === "scheduled" ? (
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={`/api/v1/interviews/${iv.id}/calendar.ics`} download>
              {t("addToCalendar")}
            </a>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <a href="#messages">{t("askToMove")}</a>
          </Button>
        </div>
      ) : null}
      <p aria-live="polite" className="text-destructive text-sm">
        {error}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------
// Offers

export function CandidateOffers({ applicationId }: { applicationId: string }) {
  const t = useTranslations("candidateHiring.offer");
  const query = useQuery({
    queryKey: candidateHiringKeys.offers(applicationId),
    queryFn: () => api.get<CandidateOffer[]>(`/applications/${applicationId}/offers/`),
  });
  if (query.isPending || (query.data && query.data.length === 0)) return null;
  return (
    <Card id="offer">
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("title")}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {query.isError ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} />
        ) : (
          query.data.map((o) => <OfferItem key={o.id} offer={o} applicationId={applicationId} />)
        )}
      </CardContent>
    </Card>
  );
}

function OfferItem({ offer: o, applicationId }: { offer: CandidateOffer; applicationId: string }) {
  const t = useTranslations("candidateHiring.offer");
  const format = useFormatter();
  const when = useWhen();
  const client = useQueryClient();
  const [accepting, setAccepting] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [declineError, setDeclineError] = useState<string | null>(null);
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: candidateHiringKeys.offers(applicationId) });
    await client.invalidateQueries({ queryKey: ["candidate", "applications"] });
  };
  const decline = useMutation({
    mutationFn: (reason: string) =>
      api.post<CandidateOffer>(
        `/offers/${o.id}/decline/`,
        { reason },
        { idempotencyKey: newIdempotencyKey() },
      ),
    onSuccess: async () => {
      setDeclining(false);
      await refresh();
    },
    onError: (err) => setDeclineError(err instanceof ApiError ? err.message : t("failed")),
  });
  const open = canRespond(o);
  const amount = Number(o.salary_amount);
  const salary = Number.isFinite(amount)
    ? format.number(amount, { style: "currency", currency: o.currency || "USD" })
    : `${o.currency} ${o.salary_amount}`;
  const status = t.has(`status.${o.status}`) ? t(`status.${o.status}`) : o.status;
  return (
    <section className="flex flex-col gap-3" aria-label={o.job_title}>
      <p className="font-medium">
        {o.job_title} · {o.organisation_name} ·{" "}
        <span className="text-muted-foreground">{status}</span>
      </p>
      <dl className="grid gap-1 text-sm sm:grid-cols-[minmax(0,12rem)_1fr]">
        <dt className="text-muted-foreground">{t("salary")}</dt>
        <dd>
          {salary}
          {o.period ? ` ${t.has(`period.${o.period}`) ? t(`period.${o.period}`) : o.period}` : ""}
        </dd>
        <dt className="text-muted-foreground">{t("startDate")}</dt>
        <dd>{format.dateTime(new Date(`${o.start_date}T00:00:00`), { dateStyle: "long" })}</dd>
        {o.contract_type ? (
          <>
            <dt className="text-muted-foreground">{t("contract")}</dt>
            <dd>{o.contract_type}</dd>
          </>
        ) : null}
        {o.status === "issued" ? (
          <>
            <dt className="text-muted-foreground">{t("respondBy")}</dt>
            <dd>{when(o.expires_at)}</dd>
          </>
        ) : null}
      </dl>
      {o.conditions ? (
        <div className="text-sm">
          <h3 className="font-medium">{t("conditions")}</h3>
          <p className="whitespace-pre-line">{o.conditions}</p>
        </div>
      ) : null}
      {o.letter_document_id ? (
        <p className="text-sm">
          <a className="underline" href={`/api/v1/documents/${o.letter_document_id}/download/`}>
            {t("letter")}
          </a>
        </p>
      ) : null}
      {o.status === "accepted" ? (
        <p className="text-sm" role="status">
          {t("acceptedNote")}
        </p>
      ) : null}
      {o.status === "issued" && !open ? <p className="text-sm">{t("expiredNote")}</p> : null}

      {open && !accepting ? (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setAccepting(true)}>{t("accept")}</Button>
          <Button variant="outline" onClick={() => setDeclining(true)}>
            {t("decline")}
          </Button>
        </div>
      ) : null}
      {open && accepting ? (
        <AcceptOfferForm offer={o} onCancel={() => setAccepting(false)} onDone={refresh} />
      ) : null}
      {declining ? (
        <ConfirmDialog
          open
          onOpenChange={(v) => !v && setDeclining(false)}
          title={t("declineTitle")}
          description={t("declineBody")}
          confirmLabel={t("decline")}
          destructive
          reason="optional"
          pending={decline.isPending}
          error={declineError}
          onConfirm={(reason) => decline.mutate(reason)}
        />
      ) : null}
    </section>
  );
}

export const acceptSchema = z.object({
  typed_name: z.string().trim().min(2, "required").max(200, "tooLong"),
  agree: z.boolean().refine((v) => v, "mustAgreeOffer"),
  counter_offer_note: z.string().max(2000, "tooLong"),
});
type AcceptValues = z.infer<typeof acceptSchema>;

function AcceptOfferForm({
  offer,
  onCancel,
  onDone,
}: {
  offer: CandidateOffer;
  onCancel: () => void;
  onDone: () => Promise<void>;
}) {
  const t = useTranslations("candidateHiring.offer");
  const errorText = useErrorText();
  const [formError, setFormError] = useState<string | null>(null);
  // One key per form: a retried submit after a network drop is the same acceptance.
  const [idempotencyKey] = useState(newIdempotencyKey);
  const form = useForm<AcceptValues>({
    resolver: zodResolver(acceptSchema),
    defaultValues: { typed_name: "", agree: false, counter_offer_note: "" },
  });
  const accept = useMutation({
    mutationFn: (values: AcceptValues) =>
      api.post<CandidateOffer>(`/offers/${offer.id}/accept/`, values, { idempotencyKey }),
    onSuccess: onDone,
    onError: (err) =>
      setFormError(
        applyServerErrors(err, form.setError, {
          typed_name: "typed_name",
          agree: "agree",
          counter_offer_note: "counter_offer_note",
        }),
      ),
  });
  const e = form.formState.errors;
  const agreeError = errorText(e.agree?.message);
  return (
    <form
      noValidate
      className="flex flex-col gap-4 rounded-md border p-4"
      aria-label={t("acceptTitle")}
      onSubmit={form.handleSubmit((values) => {
        setFormError(null);
        accept.mutate(values);
      })}
    >
      <h3 className="font-medium">{t("acceptTitle")}</h3>
      <ErrorSummary
        errors={e}
        formError={formError}
        submitCount={form.formState.submitCount}
        labels={{
          typed_name: t("typedName"),
          agree: t("agreeLabel"),
          counter_offer_note: t("counterNote"),
        }}
      />
      <TextField
        label={t("typedName")}
        description={t("typedNameHelp")}
        required
        autoComplete="name"
        error={e.typed_name}
        {...form.register("typed_name")}
      />
      <div className="flex flex-col gap-1.5">
        <div className="flex items-start gap-2">
          <input
            id="field-agree"
            type="checkbox"
            className="mt-1 size-5"
            aria-invalid={agreeError ? true : undefined}
            aria-describedby={agreeError ? "field-agree-err" : undefined}
            {...form.register("agree")}
          />
          <Label htmlFor="field-agree" className="leading-snug font-normal">
            {offer.acceptance_statement || t("defaultStatement")}
          </Label>
        </div>
        {agreeError ? (
          <p id="field-agree-err" className="text-destructive text-sm" role="alert">
            {agreeError}
          </p>
        ) : null}
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="field-counter_offer_note">{t("counterNote")}</Label>
        <textarea
          id="field-counter_offer_note"
          rows={3}
          className="border-input bg-background rounded-md border p-2 text-sm"
          aria-describedby="field-counter_offer_note-desc"
          {...form.register("counter_offer_note")}
        />
        <p id="field-counter_offer_note-desc" className="text-muted-foreground text-xs">
          {t("counterNoteHelp")}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={accept.isPending}>
          {t("confirmAccept")}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
