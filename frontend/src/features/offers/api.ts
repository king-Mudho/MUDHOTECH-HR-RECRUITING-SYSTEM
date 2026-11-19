"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useJobsContext } from "@/features/jobs/hooks";
import { api, newIdempotencyKey } from "@/lib/api-client";
import type { components } from "@/types/api";

export type Offer = components["schemas"]["Offer"];
export type OfferTerms = components["schemas"]["OfferTermsRequest"];
export type HireResult = components["schemas"]["HireResult"];
export type CloseoutPreview = components["schemas"]["CloseoutPreview"];
export type CloseoutResult = components["schemas"]["CloseoutResult"];
export type DecisionReason = components["schemas"]["DecisionReason"];
type Page = components["schemas"]["PaginatedOfferList"];

export const OFFER_VIEWERS = ["org_admin", "hr_manager", "recruiter", "hiring_manager"];
export const OFFER_MANAGERS = ["org_admin", "hr_manager", "recruiter"];
export const OFFER_APPROVERS = ["org_admin", "hr_manager"];

export const offerKeys = {
  all: (orgId: string) => ["offers", orgId] as const,
  list: (orgId: string, status: string) => ["offers", orgId, "list", status] as const,
  detail: (orgId: string, id: string) => ["offers", orgId, id] as const,
  forApplication: (orgId: string, appId: string) =>
    ["offers", orgId, "application", appId] as const,
  closeout: (orgId: string, jobId: string) => ["offers", orgId, "closeout", jobId] as const,
};

export function useOffers(status: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: offerKeys.list(orgId ?? "", status),
    queryFn: () =>
      api.get<Page>("/hr/offers/", {
        orgId: orgId!,
        query: { status: status || undefined, page_size: 100 },
      }),
    enabled: !!orgId,
  });
}

export function useOffer(id: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: offerKeys.detail(orgId ?? "", id),
    queryFn: () => api.get<Offer>(`/hr/offers/${id}/`, { orgId: orgId! }),
    enabled: !!orgId,
  });
}

export function useApplicationOffers(appId: string, enabled = true) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: offerKeys.forApplication(orgId ?? "", appId),
    queryFn: () => api.get<Offer[]>(`/hr/applications/${appId}/offers/`, { orgId: orgId! }),
    enabled: !!orgId && enabled,
  });
}

export function useCloseout(jobId: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: offerKeys.closeout(orgId ?? "", jobId),
    queryFn: () => api.get<CloseoutPreview>(`/hr/jobs/${jobId}/closeout/`, { orgId: orgId! }),
    enabled: !!orgId,
  });
}

export function useNotSelectedReasons() {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: ["hr-decision-reasons", orgId ?? "", "not_selected"],
    queryFn: () =>
      api.get<DecisionReason[]>("/hr/decision-reasons/", {
        orgId: orgId!,
        query: { applies_to: "not_selected" },
      }),
    enabled: !!orgId,
    staleTime: 5 * 60_000,
  });
}

export function useOfferMutation<TBody, TResult>(
  path: (body: TBody) => string,
  method: "post" | "patch" = "post",
) {
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: TBody) =>
      method === "patch"
        ? api.patch<TResult>(path(body), body, { orgId: orgId! })
        : api.post<TResult>(path(body), body, {
            orgId: orgId!,
            idempotencyKey: newIdempotencyKey(),
          }),
    onSuccess: () => {
      if (!orgId) return;
      void client.invalidateQueries({ queryKey: offerKeys.all(orgId) });
      void client.invalidateQueries({ queryKey: ["hr-applications"] });
    },
  });
}

/** Which actions a role may take on an offer in its current state (the server enforces them too). */
export function offerActions(offer: Pick<Offer, "status" | "hire_recorded">, role: string | null) {
  const manage = !!role && OFFER_MANAGERS.includes(role);
  const approve = !!role && OFFER_APPROVERS.includes(role);
  const s = offer.status;
  return {
    edit: manage && s === "draft",
    submit: manage && s === "draft",
    approve: approve && s === "pending_approval",
    giveBack: approve && (s === "pending_approval" || s === "approved"),
    issue: manage && s === "approved",
    withdraw:
      approve && ["draft", "pending_approval", "approved", "issued", "accepted"].includes(s),
    hire: approve && s === "accepted" && !offer.hire_recorded,
  };
}
