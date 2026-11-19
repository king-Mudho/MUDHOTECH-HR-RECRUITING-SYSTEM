"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api } from "@/lib/api-client";
import { downloadWithOrg } from "@/lib/download";
import type { components } from "@/types/api";

import { billingKey, type BillingOverview } from "./components";

type Invoice = components["schemas"]["Invoice"];
type Payment = components["schemas"]["Payment"];
type PayResult = components["schemas"]["PayResult"];

const FINAL = ["paid", "failed", "cancelled", "pending_manual_check"];

export function money(amount: string | number, currency: string): string {
  const n = Number(amount);
  return `${currency} ${Number.isFinite(n) ? n.toFixed(2) : amount}`;
}

/** Polls a payment until it reaches a final state (mobile money / return from Paynow). */
function PaymentStatus({ paymentId }: { paymentId: string }) {
  const t = useTranslations("billing.pay");
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const q = useQuery({
    queryKey: ["billing", orgId ?? "", "payment", paymentId],
    queryFn: async () => {
      const p = await api.get<Payment>(`/hr/billing/payments/${paymentId}/`, { orgId: orgId! });
      if (FINAL.includes(p.status)) {
        // only the overview and the invoice list - never this payment query (no refetch loop)
        void client.invalidateQueries({ queryKey: billingKey(orgId ?? ""), exact: true });
        void client.invalidateQueries({ queryKey: [...billingKey(orgId ?? ""), "invoices"] });
      }
      return p;
    },
    enabled: !!orgId,
    refetchInterval: (query) =>
      query.state.data && FINAL.includes(query.state.data.status) ? false : 5000,
  });
  if (!q.data) return null;
  return (
    <p role="status" className="text-sm">
      {t(`status.${FINAL.includes(q.data.status) ? q.data.status : "waiting"}`)}
    </p>
  );
}

function PayForm({ invoice, onDone }: { invoice: Invoice; onDone: () => void }) {
  const t = useTranslations("billing.pay");
  const { orgId } = useJobsContext();
  const [method, setMethod] = useState("ecocash");
  const [phone, setPhone] = useState("");
  const [started, setStarted] = useState<PayResult | null>(null);
  const ids = { method: useId(), phone: useId() };
  const pay = useMutation({
    mutationFn: () =>
      api.post<PayResult>(
        `/hr/billing/invoices/${invoice.id}/pay/`,
        { method, phone: method === "card" ? "" : phone },
        { orgId: orgId! },
      ),
    onSuccess: (res) => {
      if (res.redirect_url) {
        window.location.assign(res.redirect_url); // Paynow's own page (cards never touch us)
        return;
      }
      setStarted(res);
    },
  });
  if (started) {
    return (
      <div className="flex flex-col gap-2 rounded-md border p-3 text-sm">
        <p>{started.instructions || t("checkPhone")}</p>
        <PaymentStatus paymentId={started.payment.id} />
        <Button size="sm" variant="ghost" className="self-start" onClick={onDone}>
          {t("close")}
        </Button>
      </div>
    );
  }
  return (
    <form
      className="flex flex-wrap items-end gap-2 rounded-md border p-3"
      onSubmit={(e) => {
        e.preventDefault();
        pay.mutate();
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={ids.method}>{t("method")}</Label>
        <select
          id={ids.method}
          className="border-input bg-background h-10 rounded-md border px-2 text-sm"
          value={method}
          onChange={(e) => setMethod(e.target.value)}
        >
          <option value="ecocash">EcoCash</option>
          <option value="onemoney">OneMoney</option>
          <option value="card">{t("card")}</option>
        </select>
      </div>
      {method !== "card" ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={ids.phone}>{t("phone")}</Label>
          <Input
            id={ids.phone}
            className="h-10"
            inputMode="tel"
            autoComplete="tel"
            placeholder="077 123 4567"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>
      ) : null}
      <Button
        type="submit"
        className="h-10"
        disabled={pay.isPending || (method !== "card" && phone.trim().length < 9)}
      >
        {t("submit", { amount: money(invoice.amount, invoice.currency) })}
      </Button>
      <Button type="button" variant="ghost" className="h-10" onClick={onDone}>
        {t("cancel")}
      </Button>
      {pay.error ? (
        <p role="alert" className="text-destructive w-full text-sm">
          {pay.error instanceof ApiError ? pay.error.message : t("failed")}
        </p>
      ) : null}
    </form>
  );
}

export function Invoices() {
  const t = useTranslations("billing.invoices");
  const format = useFormatter();
  const { orgId } = useJobsContext();
  const [paying, setPaying] = useState<string | null>(null);
  const params = useSearchParams();
  const returned = params.get("payment");
  const invoices = useQuery({
    queryKey: [...billingKey(orgId ?? ""), "invoices"],
    queryFn: () => api.get<Invoice[]>("/hr/billing/invoices/", { orgId: orgId! }),
    enabled: !!orgId,
  });
  const date = (iso: string | null | undefined) =>
    iso ? format.dateTime(new Date(iso), { dateStyle: "medium" }) : "";
  return (
    <section aria-labelledby="invoices" className="flex flex-col gap-3 rounded-lg border p-4">
      <h2 id="invoices" className="text-lg font-semibold">
        {t("title")}
      </h2>
      {returned ? <PaymentStatus paymentId={returned} /> : null}
      {!invoices.data || invoices.data.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("none")}</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {invoices.data.map((inv) => (
            <li key={inv.id} className="flex flex-col gap-2 rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{inv.number}</span>
                <span className="tabular-nums">{money(inv.amount, inv.currency)}</span>
                <Badge variant={inv.status === "open" ? "destructive" : "outline"}>
                  {t(`status.${inv.status}`)}
                </Badge>
                <span className="text-muted-foreground">
                  {inv.status === "paid"
                    ? t("paidOn", { date: date(inv.paid_at) })
                    : t("dueOn", { date: date(inv.due_at) })}
                </span>
                <span className="ml-auto flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void downloadWithOrg(
                        `/api/v1/hr/billing/invoices/${inv.id}/pdf/`,
                        orgId!,
                        `${inv.number}.pdf`,
                      )
                    }
                  >
                    {t("download")}
                  </Button>
                  {inv.status === "open" && paying !== inv.id ? (
                    <Button size="sm" onClick={() => setPaying(inv.id)}>
                      {t("payNow")}
                    </Button>
                  ) : null}
                </span>
              </div>
              {paying === inv.id ? <PayForm invoice={inv} onDone={() => setPaying(null)} /> : null}
            </li>
          ))}
        </ul>
      )}
      <p className="text-muted-foreground text-xs">{t("bankTransfer")}</p>
    </section>
  );
}

export function ChangePlan({ data }: { data: BillingOverview }) {
  const t = useTranslations("billing.plans");
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const [currency, setCurrency] = useState(data.subscription.currency || "USD");
  const id = useId();
  const choose = useMutation({
    mutationFn: (plan: string) =>
      api.post<Invoice>("/hr/billing/change-plan/", { plan, currency }, { orgId: orgId! }),
    onSuccess: () => client.invalidateQueries({ queryKey: billingKey(orgId ?? "") }),
  });
  return (
    <section aria-labelledby="plans" className="flex flex-col gap-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="plans" className="text-lg font-semibold">
          {t("title")}
        </h2>
        <div className="flex items-center gap-2 text-sm">
          <Label htmlFor={id}>{t("currency")}</Label>
          <select
            id={id}
            className="border-input bg-background h-9 rounded-md border px-2"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            <option value="USD">USD</option>
            <option value="ZWG">ZWG</option>
          </select>
        </div>
      </div>
      <ul className="grid gap-3 sm:grid-cols-3">
        {data.plans.map((p) => {
          const price = currency === "USD" ? p.price_usd : p.price_zwg;
          const current = p.code === data.plan.code && data.subscription.status === "active";
          return (
            <li key={p.code} className="flex flex-col gap-2 rounded-md border p-3 text-sm">
              <span className="font-semibold">{p.name}</span>
              <span className="text-lg tabular-nums">
                {price === null ? t("custom") : t("perMonth", { price: money(price, currency) })}
              </span>
              <span className="text-muted-foreground">{p.description}</span>
              <ul className="text-xs">
                {Object.entries(p.limits).map(([k, v]) => (
                  <li key={k}>
                    {t(`limits.${k}`, { value: v === null ? t("unlimited") : String(v) })}
                  </li>
                ))}
              </ul>
              {current ? (
                <Badge variant="outline" className="self-start">
                  {t("current")}
                </Badge>
              ) : price === null ? (
                <a className="text-sm underline" href="mailto:billing@mudhotech.co.zw">
                  {t("contact")}
                </a>
              ) : (
                <Button
                  size="sm"
                  className="self-start"
                  disabled={choose.isPending}
                  onClick={() => choose.mutate(p.code)}
                >
                  {t("choose")}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      <p className="text-muted-foreground text-xs">{t("how")}</p>
      <p aria-live="polite" className="text-sm">
        {choose.isSuccess ? t("invoiced") : null}
        {choose.error ? (
          <span className="text-destructive">
            {choose.error instanceof ApiError ? choose.error.message : t("failed")}
          </span>
        ) : null}
      </p>
    </section>
  );
}
