"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useJobsContext } from "@/features/jobs/hooks";
import { api, newIdempotencyKey } from "@/lib/api-client";
import type { components } from "@/types/api";

export type Interview = components["schemas"]["Interview"];
export type Scheduled = components["schemas"]["Scheduled"];
export type PanelView = components["schemas"]["PanelView"];
export type Scorecard = components["schemas"]["Scorecard"];
export type Feedback = components["schemas"]["Feedback"];
export type ScorecardTemplate = components["schemas"]["ScorecardTemplate"];
export type PanelOption = components["schemas"]["PanelOption"];
export type InterviewCreate = components["schemas"]["InterviewCreateRequest"];
export type ScorecardInput = components["schemas"]["ScorecardInRequest"];
type Page = components["schemas"]["PaginatedInterviewList"];

export const MANAGERS = ["org_admin", "hr_manager", "recruiter"];
export const VIEW_ALL = [...MANAGERS, "hiring_manager"];
export const FEEDBACK = VIEW_ALL;

export const interviewKeys = {
  all: (orgId: string) => ["interviews", orgId] as const,
  list: (orgId: string, params: ListParams) => ["interviews", orgId, "list", params] as const,
  detail: (orgId: string, id: string) => ["interviews", orgId, id] as const,
  scorecards: (orgId: string, id: string) => ["interviews", orgId, id, "scorecards"] as const,
  feedback: (orgId: string, id: string) => ["interviews", orgId, id, "feedback"] as const,
  forApplication: (orgId: string, appId: string) =>
    ["interviews", orgId, "application", appId] as const,
  templates: (orgId: string, jobId: string) => ["interviews", orgId, "templates", jobId] as const,
  panelOptions: (orgId: string) => ["interviews", orgId, "panel-options"] as const,
};

export interface ListParams {
  from: string;
  to: string;
  mine: boolean;
}

export function useInterviewList(params: ListParams) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: interviewKeys.list(orgId ?? "", params),
    queryFn: () =>
      api.get<Page>("/hr/interviews/", {
        orgId: orgId!,
        query: { from: params.from, to: params.to, mine: params.mine, page_size: 100 },
      }),
    enabled: !!orgId,
  });
}

export function useInterview(id: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: interviewKeys.detail(orgId ?? "", id),
    queryFn: () => api.get<PanelView>(`/hr/interviews/${id}/`, { orgId: orgId! }),
    enabled: !!orgId,
  });
}

export function useScorecards(id: string, enabled = true) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: interviewKeys.scorecards(orgId ?? "", id),
    queryFn: () => api.get<Scorecard[]>(`/hr/interviews/${id}/scorecards/`, { orgId: orgId! }),
    enabled: !!orgId && enabled,
  });
}

export function useFeedback(id: string, enabled: boolean) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: interviewKeys.feedback(orgId ?? "", id),
    queryFn: () => api.get<Feedback>(`/hr/interviews/${id}/feedback/`, { orgId: orgId! }),
    enabled: !!orgId && enabled,
  });
}

export function useApplicationInterviews(appId: string, enabled = true) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: interviewKeys.forApplication(orgId ?? "", appId),
    queryFn: () => api.get<Interview[]>(`/hr/applications/${appId}/interviews/`, { orgId: orgId! }),
    enabled: !!orgId && enabled,
  });
}

export function useTemplates(jobId: string, enabled = true) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: interviewKeys.templates(orgId ?? "", jobId),
    queryFn: () =>
      api.get<ScorecardTemplate[]>(`/hr/jobs/${jobId}/scorecard-templates/`, { orgId: orgId! }),
    enabled: !!orgId && enabled,
  });
}

export function usePanelOptions(enabled = true) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: interviewKeys.panelOptions(orgId ?? ""),
    queryFn: () => api.get<PanelOption[]>("/hr/interviews/panel-options/", { orgId: orgId! }),
    enabled: !!orgId && enabled,
    staleTime: 5 * 60_000,
  });
}

/** POST helpers that refresh every interview query of the organisation afterwards. */
export function useInterviewMutation<TBody, TResult>(
  path: (body: TBody) => string,
  method: "post" | "put" = "post",
) {
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: TBody) =>
      method === "put"
        ? api.put<TResult>(path(body), body, { orgId: orgId! })
        : api.post<TResult>(path(body), body, {
            orgId: orgId!,
            idempotencyKey: newIdempotencyKey(),
          }),
    onSuccess: () => {
      if (orgId) void client.invalidateQueries({ queryKey: interviewKeys.all(orgId) });
    },
  });
}

// ---------------------------------------------------------------------------------------- helpers
/** Monday 00:00 (local) of the week containing `day`. */
export function weekStart(day: Date): Date {
  const d = new Date(day.getFullYear(), day.getMonth(), day.getDate());
  const offset = (d.getDay() + 6) % 7; // Monday = 0
  d.setDate(d.getDate() - offset);
  return d;
}

export function addDays(day: Date, n: number): Date {
  const d = new Date(day);
  d.setDate(d.getDate() + n);
  return d;
}

/** Interviews grouped by local calendar day (YYYY-MM-DD), proposed ones (no time yet) last. */
export function groupByDay(rows: Interview[]): { day: string | null; items: Interview[] }[] {
  const groups = new Map<string | null, Interview[]>();
  const sorted = [...rows].sort((a, b) =>
    (a.starts_at ?? "9999").localeCompare(b.starts_at ?? "9999"),
  );
  for (const iv of sorted) {
    const key = iv.starts_at ? localDay(new Date(iv.starts_at)) : null;
    groups.set(key, [...(groups.get(key) ?? []), iv]);
  }
  return [...groups.entries()].map(([day, items]) => ({ day, items }));
}

export function localDay(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** `datetime-local` input value (local time) -> ISO string with the browser's offset. */
export function fromLocalInput(value: string): string {
  return new Date(value).toISOString();
}
