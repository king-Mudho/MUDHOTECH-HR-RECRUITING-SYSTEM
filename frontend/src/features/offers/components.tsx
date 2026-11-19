"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { applyServerErrors } from "@/features/auth/form-errors";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError } from "@/lib/api-client";
import { downloadWithOrg } from "@/lib/download";

import {
  OFFER_MANAGERS,
  OFFER_VIEWERS,
  offerActions,
  useApplicationOffers,
  useCloseout,
  useNotSelectedReasons,
  useOffer,
  useOfferMutation,
  useOffers,
  type CloseoutResult,
  type HireResult,
  type Offer,
} from "./api";

const STATUSES = [
  "",
  "draft",
  "pending_approval",
  "approved",
  "issued",
  "accepted",
  "declined",
  "expired",
  "withdrawn",
];
const CURRENCIES = ["USD", "ZWG"] as const;
const PERIODS = ["month", "year", "day", "hour"] as const;
const CONTRACTS = [
  "full_time",
  "part_time",
  "contract",
  "temporary",
  "internship",
  "attachment",
] as const;

function errorText(err: unknown, fallback: string): string | null {
  return err instanceof ApiError ? err.message : err ? fallback : null;
}

function useMoney() {
  const format = useFormatter();
  return (amount: string, currency: string) => {
    const n = Number(amount);
    return `${currency} ${format.number(n, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };
}

// ------------------------------------------------------------------------------ list
export function OffersRoute() {
  const t = useTranslations("offers");
  const { role, isPending } = useJobsContext();
  const [status, setStatus] = useState("");
  const offers = useOffers(status);
  const money = useMoney();
  if (isPending) return <PageSkeleton />;
  if (!role || !OFFER_VIEWERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <div role="group" aria-label={t("filter")} className="flex flex-wrap gap-1">
        {STATUSES.map((s) => (
          <Button
            key={s || "all"}
            size="sm"
            variant={status === s ? "default" : "outline"}
            aria-pressed={status === s}
            onClick={() => setStatus(s)}
          >
            {s ? t(`status.${s}`) : t("all")}
          </Button>
        ))}
      </div>
      {offers.isPending ? (
        <PageSkeleton />
      ) : offers.isError ? (
        <ErrorState error={offers.error} onRetry={() => offers.refetch()} />
      ) : offers.data.results.length === 0 ? (
        <EmptyState title={t("emptyTitle")} description={t("empty")} />
      ) : (
        <ul className="flex flex-col gap-2">
          {offers.data.results.map((o) => (
            <li key={o.id}>
              <Link
                href={`/hr/offers/${o.id}`}
                className="hover:bg-muted flex flex-wrap items-center gap-3 rounded-lg border p-3"
              >
                <span className="flex-1">
                  <span className="font-medium">{o.job_title}</span>
                  <span className="text-muted-foreground text-sm"> · {o.reference}</span>
                </span>
                <span className="text-sm">{money(o.salary_amount, o.currency)}</span>
                <Badge variant={o.status === "accepted" ? "default" : "secondary"}>
                  {t(`status.${o.status}`)}
                </Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------ detail
export function OfferDetailRoute() {
  const { id } = useParams<{ id: string }>();
  return <OfferDetail id={id} />;
}

function OfferDetail({ id }: { id: string }) {
  const t = useTranslations("offers");
  const format = useFormatter();
  const money = useMoney();
  const { role, orgId } = useJobsContext();
  const offer = useOffer(id);
  const [dialog, setDialog] = useState<"" | "return" | "withdraw" | "issue">("");
  const [hire, setHire] = useState<HireResult | null>(null);
  const submit = useOfferMutation<Record<string, never>, Offer>(() => `/hr/offers/${id}/submit/`);
  const approve = useOfferMutation<{ comment: string }, Offer>(() => `/hr/offers/${id}/approve/`);
  const giveBack = useOfferMutation<{ comment: string }, Offer>(() => `/hr/offers/${id}/return/`);
  const issue = useOfferMutation<Record<string, never>, Offer>(() => `/hr/offers/${id}/issue/`);
  const withdraw = useOfferMutation<{ reason: string }, Offer>(() => `/hr/offers/${id}/withdraw/`);
  const record = useOfferMutation<{ note: string }, HireResult>(() => `/hr/offers/${id}/hire/`);
  if (offer.isPending) return <PageSkeleton />;
  if (offer.isError) return <ErrorState error={offer.error} onRetry={() => offer.refetch()} />;
  const o = offer.data;
  const can = offerActions(o, role);
  const error = errorText(
    submit.error ??
      approve.error ??
      giveBack.error ??
      issue.error ??
      withdraw.error ??
      record.error,
    t("failed"),
  );
  const rows: [string, string][] = [
    [t("salary"), `${money(o.salary_amount, o.currency)} ${t(`period.${o.period}`)}`],
    [t("contract"), t(`contractType.${o.contract_type}`)],
    [t("startDate"), format.dateTime(new Date(`${o.start_date}T12:00:00`), { dateStyle: "long" })],
    [
      t("expires"),
      format.dateTime(new Date(o.expires_at), { dateStyle: "long", timeStyle: "short" }),
    ],
    [
      t("approvalsLabel"),
      t("approvalsCount", { required: o.required_approvals, round: o.approval_round }),
    ],
  ];
  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link href="/hr/offers" className="text-sm underline">
          {t("back")}
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">
          {o.job_title} ·{" "}
          <Link href={`/hr/applications/${o.application_id}`} className="underline">
            {o.reference}
          </Link>
        </h1>
        <Badge className="mt-1">{t(`status.${o.status}`)}</Badge>
      </div>
      {o.openings.over ? (
        <Alert>
          <AlertTitle>{t("overTitle")}</AlertTitle>
          <AlertDescription>
            {t("over", { accepted: o.openings.accepted, openings: o.openings.openings })}
          </AlertDescription>
        </Alert>
      ) : null}
      <section aria-labelledby="offer-terms" className="rounded-lg border p-4">
        <h2 id="offer-terms" className="text-lg font-semibold">
          {t("terms")}
        </h2>
        <dl className="mt-2 grid gap-1 sm:grid-cols-[12rem_1fr]">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="font-medium">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
        {o.conditions ? <p className="mt-2 text-sm whitespace-pre-line">{o.conditions}</p> : null}
        {o.counter_offer_note ? (
          <p className="mt-2 text-sm">
            <span className="font-medium">{t("candidateNote")}: </span>
            {o.counter_offer_note}
          </p>
        ) : null}
        {o.decline_reason ? (
          <p className="mt-2 text-sm">
            <span className="font-medium">{t("declineReason")}: </span>
            {o.decline_reason}
          </p>
        ) : null}
        {o.close_reason ? (
          <p className="text-muted-foreground mt-2 text-sm">{o.close_reason}</p>
        ) : null}
      </section>
      {can.edit ? <OfferForm applicationId={o.application_id} offer={o} /> : null}
      <section aria-labelledby="offer-approvals" className="rounded-lg border p-4">
        <h2 id="offer-approvals" className="text-lg font-semibold">
          {t("approvals")}
        </h2>
        {o.approvals.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("noApprovals")}</p>
        ) : (
          <ul className="mt-1 text-sm">
            {o.approvals.map((a, i) => (
              <li key={i}>
                {t(`decision.${a.decision}`)} · {a.approver} · {t("round", { n: a.round })}
                {a.comment ? ` — ${a.comment}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>
      <div className="flex flex-wrap gap-2">
        {can.submit ? (
          <Button onClick={() => submit.mutate({})} disabled={submit.isPending}>
            {t("submit")}
          </Button>
        ) : null}
        {can.approve ? (
          <Button onClick={() => approve.mutate({ comment: "" })} disabled={approve.isPending}>
            {t("approve")}
          </Button>
        ) : null}
        {can.giveBack ? (
          <Button variant="outline" onClick={() => setDialog("return")}>
            {t("giveBack")}
          </Button>
        ) : null}
        {can.issue ? <Button onClick={() => setDialog("issue")}>{t("issue")}</Button> : null}
        {o.has_letter && orgId ? (
          <Button
            variant="outline"
            onClick={() =>
              void downloadWithOrg(
                `/api/v1/hr/offers/${o.id}/letter/`,
                orgId,
                `offer-letter-${o.reference ?? o.id}.pdf`,
              )
            }
          >
            {t("letter")}
          </Button>
        ) : null}
        {can.hire ? (
          <Button
            onClick={() => record.mutate({ note: "" }, { onSuccess: setHire })}
            disabled={record.isPending}
          >
            {t("recordHire")}
          </Button>
        ) : null}
        {can.withdraw ? (
          <Button variant="outline" onClick={() => setDialog("withdraw")}>
            {t("withdraw")}
          </Button>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      {hire ? (
        <Alert role="status">
          <AlertTitle>{t("hired")}</AlertTitle>
          <AlertDescription>
            {t("hiredOpenings", { remaining: hire.openings.remaining })}
            {hire.prompt_close ? (
              <span className="mt-2 flex flex-wrap gap-2">
                <Link className="underline" href={`/hr/jobs/${o.job_id}`}>
                  {t("closeVacancy")}
                </Link>
                <Link className="underline" href={`/hr/jobs/${o.job_id}/closeout`}>
                  {t("notifyOthers")}
                </Link>
              </span>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}
      <ConfirmDialog
        open={dialog === "issue"}
        onOpenChange={(open) => setDialog(open ? "issue" : "")}
        title={t("issueTitle")}
        description={t("issueHelp")}
        confirmLabel={t("issue")}
        pending={issue.isPending}
        onConfirm={() => issue.mutate({}, { onSuccess: () => setDialog("") })}
      />
      <ConfirmDialog
        open={dialog === "return"}
        onOpenChange={(open) => setDialog(open ? "return" : "")}
        title={t("giveBackTitle")}
        confirmLabel={t("giveBack")}
        reason="required"
        pending={giveBack.isPending}
        onConfirm={(comment) => giveBack.mutate({ comment }, { onSuccess: () => setDialog("") })}
      />
      <ConfirmDialog
        open={dialog === "withdraw"}
        onOpenChange={(open) => setDialog(open ? "withdraw" : "")}
        title={t("withdrawTitle")}
        description={t("withdrawHelp")}
        confirmLabel={t("withdraw")}
        destructive
        reason="required"
        pending={withdraw.isPending}
        onConfirm={(reason) => withdraw.mutate({ reason }, { onSuccess: () => setDialog("") })}
      />
    </div>
  );
}

// ------------------------------------------------------------------------------ builder
const termsSchema = z.object({
  salaryAmount: z.string().regex(/^\d+(\.\d{1,2})?$/),
  currency: z.enum(CURRENCIES),
  period: z.enum(PERIODS),
  startDate: z.string().min(1),
  contractType: z.enum(CONTRACTS),
  conditions: z.string().max(10000),
  expiresAt: z.string().min(1),
});
type TermsValues = z.infer<typeof termsSchema>;

function toInputDateTime(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function OfferForm({
  applicationId,
  offer,
  onDone,
}: {
  applicationId: string;
  offer?: Offer;
  onDone?: () => void;
}) {
  const t = useTranslations("offers.form");
  const to = useTranslations("offers");
  const ids = {
    amount: useId(),
    currency: useId(),
    period: useId(),
    start: useId(),
    contract: useId(),
    conditions: useId(),
    expires: useId(),
  };
  const form = useForm<TermsValues>({
    resolver: zodResolver(termsSchema),
    defaultValues: offer
      ? {
          salaryAmount: offer.salary_amount,
          currency: offer.currency as TermsValues["currency"],
          period: offer.period as TermsValues["period"],
          startDate: offer.start_date,
          contractType: offer.contract_type as TermsValues["contractType"],
          conditions: offer.conditions,
          expiresAt: toInputDateTime(offer.expires_at),
        }
      : {
          salaryAmount: "",
          currency: "USD",
          period: "month",
          startDate: "",
          contractType: "full_time",
          conditions: "",
          expiresAt: "",
        },
  });
  const [formError, setFormError] = useState<string | null>(null);
  const create = useOfferMutation<Record<string, unknown>, Offer>(
    () => `/hr/applications/${applicationId}/offers/`,
  );
  const update = useOfferMutation<Record<string, unknown>, Offer>(
    () => `/hr/offers/${offer?.id}/`,
    "patch",
  );
  const errors = form.formState.errors;
  const submit = form.handleSubmit((v) => {
    const body = {
      salary_amount: v.salaryAmount,
      currency: v.currency,
      period: v.period,
      start_date: v.startDate,
      contract_type: v.contractType,
      conditions: v.conditions,
      expires_at: new Date(v.expiresAt).toISOString(),
      ...(offer ? { lock_version: offer.lock_version } : {}),
    };
    const call = offer ? update : create;
    call.mutate(body, {
      onSuccess: () => onDone?.(),
      onError: (err) =>
        setFormError(
          applyServerErrors(err, form.setError, {
            salary_amount: "salaryAmount",
            start_date: "startDate",
            expires_at: "expiresAt",
            contract_type: "contractType",
          }),
        ),
    });
  });
  return (
    <form
      onSubmit={submit}
      noValidate
      className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2"
      aria-label={offer ? t("editTitle") : t("newTitle")}
    >
      <h2 className="text-lg font-semibold sm:col-span-2">
        {offer ? t("editTitle") : t("newTitle")}
      </h2>
      <div className="flex flex-col gap-1">
        <Label htmlFor={ids.amount}>{t("amount")}</Label>
        <Input id={ids.amount} inputMode="decimal" {...form.register("salaryAmount")} />
        {errors.salaryAmount ? (
          <p className="text-destructive text-xs">
            {errors.salaryAmount.message?.length && errors.salaryAmount.type === "server"
              ? errors.salaryAmount.message
              : t("amountInvalid")}
          </p>
        ) : null}
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={ids.currency}>{t("currency")}</Label>
        <select
          id={ids.currency}
          className="h-9 rounded border px-2"
          {...form.register("currency")}
        >
          {CURRENCIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={ids.period}>{t("period")}</Label>
        <select id={ids.period} className="h-9 rounded border px-2" {...form.register("period")}>
          {PERIODS.map((p) => (
            <option key={p} value={p}>
              {to(`period.${p}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={ids.contract}>{t("contract")}</Label>
        <select
          id={ids.contract}
          className="h-9 rounded border px-2"
          {...form.register("contractType")}
        >
          {CONTRACTS.map((c) => (
            <option key={c} value={c}>
              {to(`contractType.${c}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={ids.start}>{t("startDate")}</Label>
        <Input id={ids.start} type="date" {...form.register("startDate")} />
        {errors.startDate ? (
          <p className="text-destructive text-xs">
            {errors.startDate.type === "server" ? errors.startDate.message : t("required")}
          </p>
        ) : null}
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={ids.expires}>{t("expires")}</Label>
        <Input id={ids.expires} type="datetime-local" {...form.register("expiresAt")} />
        {errors.expiresAt ? (
          <p className="text-destructive text-xs">
            {errors.expiresAt.type === "server" ? errors.expiresAt.message : t("required")}
          </p>
        ) : null}
      </div>
      <div className="flex flex-col gap-1 sm:col-span-2">
        <Label htmlFor={ids.conditions}>{t("conditions")}</Label>
        <textarea
          id={ids.conditions}
          rows={4}
          className="rounded border p-2 text-sm"
          {...form.register("conditions")}
        />
        <p className="text-muted-foreground text-xs">{t("conditionsHelp")}</p>
      </div>
      {formError ? (
        <p role="alert" className="text-destructive text-sm sm:col-span-2">
          {formError}
        </p>
      ) : null}
      <div className="sm:col-span-2">
        <Button type="submit" disabled={create.isPending || update.isPending}>
          {offer ? t("save") : t("create")}
        </Button>
      </div>
    </form>
  );
}

// ------------------------------------------------------------------------------ application panel
export function ApplicationOffersPanel({
  applicationId,
  status,
}: {
  applicationId: string;
  status: string;
}) {
  const t = useTranslations("offers.panel");
  const to = useTranslations("offers");
  const money = useMoney();
  const { role } = useJobsContext();
  const relevant = ["interview", "offer", "hired", "offer_declined"].includes(status);
  const offers = useApplicationOffers(
    applicationId,
    relevant && !!role && OFFER_VIEWERS.includes(role),
  );
  const [open, setOpen] = useState(false);
  if (!relevant || !role || !OFFER_VIEWERS.includes(role)) return null;
  const live = (offers.data ?? []).some((o) =>
    ["draft", "pending_approval", "approved", "issued", "accepted"].includes(o.status),
  );
  const canCreate =
    OFFER_MANAGERS.includes(role) && (status === "interview" || status === "offer") && !live;
  return (
    <section
      id="offer"
      aria-labelledby="hr-offer"
      className="flex flex-col gap-2 rounded-lg border p-4"
    >
      <h2 id="hr-offer" className="text-lg font-semibold">
        {t("title")}
      </h2>
      {offers.isPending ? null : offers.isError ? (
        <ErrorState error={offers.error} onRetry={() => offers.refetch()} />
      ) : offers.data.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("none")}</p>
      ) : (
        <ul className="text-sm">
          {offers.data.map((o) => (
            <li key={o.id}>
              <Link className="underline" href={`/hr/offers/${o.id}`}>
                {money(o.salary_amount, o.currency)}
              </Link>{" "}
              · {to(`status.${o.status}`)}
            </li>
          ))}
        </ul>
      )}
      {canCreate ? (
        open ? (
          <OfferForm applicationId={applicationId} onDone={() => setOpen(false)} />
        ) : (
          <Button size="sm" className="self-start" onClick={() => setOpen(true)}>
            {t("make")}
          </Button>
        )
      ) : null}
    </section>
  );
}

// ------------------------------------------------------------------------------ close-out
export function CloseoutRoute() {
  const { id } = useParams<{ id: string }>();
  return <Closeout jobId={id} />;
}

function Closeout({ jobId }: { jobId: string }) {
  const t = useTranslations("offers.closeout");
  const { role } = useJobsContext();
  const preview = useCloseout(jobId);
  const reasons = useNotSelectedReasons();
  const [reason, setReason] = useState("position_filled");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<CloseoutResult | null>(null);
  const ids = { reason: useId(), note: useId() };
  const confirm = useOfferMutation<Record<string, string>, CloseoutResult>(
    () => `/hr/jobs/${jobId}/closeout/`,
  );
  if (!role || !["org_admin", "hr_manager"].includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  if (preview.isPending) return <PageSkeleton />;
  if (preview.isError)
    return <ErrorState error={preview.error} onRetry={() => preview.refetch()} />;
  const p = preview.data;
  return (
    <div className="flex flex-col gap-4">
      <Link href={`/hr/jobs/${jobId}`} className="text-sm underline">
        {t("back")}
      </Link>
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <p className="text-muted-foreground text-sm">{t("help")}</p>
      <section aria-labelledby="co-who" className="rounded-lg border p-4">
        <h2 id="co-who" className="text-lg font-semibold">
          {t("who", { count: p.to_notify })}
        </h2>
        <ul className="text-sm">
          {Object.entries(p.to_notify_by_status).map(([s, n]) => (
            <li key={s}>{t("byStatus", { status: s.replaceAll("_", " "), count: n })}</li>
          ))}
        </ul>
        {p.still_in_progress.length ? (
          <p className="mt-2 text-sm">
            {t("inProgress", {
              refs: p.still_in_progress.map((r) => r.reference ?? r.id).join(", "),
            })}
          </p>
        ) : null}
        {p.with_open_offer.length ? (
          <p className="mt-1 text-sm">
            {t("openOffers", {
              refs: p.with_open_offer.map((r) => r.reference ?? r.id).join(", "),
            })}
          </p>
        ) : null}
      </section>
      {result ? (
        <Alert role="status">
          <AlertTitle>{t("doneTitle")}</AlertTitle>
          <AlertDescription>
            {t("done", { notified: result.notified, skipped: result.skipped.length })}
          </AlertDescription>
        </Alert>
      ) : p.to_notify > 0 ? (
        <div className="flex flex-col gap-2">
          <Label htmlFor={ids.reason}>{t("reason")}</Label>
          <select
            id={ids.reason}
            className="h-9 rounded border px-2"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          >
            {(reasons.data ?? []).map((r) => (
              <option key={r.code} value={r.code}>
                {r.label}
              </option>
            ))}
          </select>
          <Label htmlFor={ids.note}>{t("note")}</Label>
          <Input id={ids.note} value={note} onChange={(e) => setNote(e.target.value)} />
          <Button className="self-start" onClick={() => setConfirming(true)}>
            {t("confirm", { count: p.to_notify })}
          </Button>
        </div>
      ) : (
        <EmptyState title={t("nobodyTitle")} description={t("nobody")} />
      )}
      {errorText(confirm.error, t("failed")) ? (
        <p role="alert" className="text-destructive text-sm">
          {errorText(confirm.error, t("failed"))}
        </p>
      ) : null}
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t("confirmTitle")}
        description={t("confirmHelp", { count: p.to_notify })}
        confirmLabel={t("confirm", { count: p.to_notify })}
        destructive
        pending={confirm.isPending}
        onConfirm={() =>
          confirm.mutate(
            { fingerprint: p.fingerprint, reason_code: reason, reason_text: note },
            {
              onSuccess: (r) => {
                setResult(r);
                setConfirming(false);
              },
              onError: () => {
                setConfirming(false);
                void preview.refetch();
              },
            },
          )
        }
      />
    </div>
  );
}
