"use client";

import { useQuery } from "@tanstack/react-query";

import { useJobsContext } from "@/features/jobs/hooks";
import type { Paginated } from "@/features/jobs/api";
import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

export type HRApplicationRow = components["schemas"]["HRApplicationList"];
export type HRApplicationDetail = components["schemas"]["HRApplicationDetail"];

export interface HRApplicationParams {
  status?: string;
  search?: string;
  page?: number;
}

/** Mirrors backend `rbac.ORG_ACTIONS["applications.view"]` — UI hiding only. */
export const APPLICATION_VIEWERS = ["org_admin", "hr_manager", "recruiter", "hiring_manager"];

export const hrApplicationKeys = {
  list: (orgId: string, jobId: string, params: HRApplicationParams) =>
    ["hr-applications", orgId, "job", jobId, params] as const,
  detail: (orgId: string, id: string) => ["hr-applications", orgId, id] as const,
};

export function useJobApplications(jobId: string, params: HRApplicationParams) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: hrApplicationKeys.list(orgId ?? "", jobId, params),
    queryFn: () =>
      api.get<Paginated<HRApplicationRow>>(`/hr/jobs/${jobId}/applications/`, {
        orgId: orgId!,
        query: { ...params },
      }),
    enabled: !!orgId,
  });
}

export function useHRApplication(id: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: hrApplicationKeys.detail(orgId ?? "", id),
    queryFn: () => api.get<HRApplicationDetail>(`/hr/applications/${id}/`, { orgId: orgId! }),
    enabled: !!orgId,
  });
}

// ------------------------------------------------------------------- ATS (P05-T07/T08)
export type Note = components["schemas"]["Note"];
export type Clarification = components["schemas"]["Clarification"];
export type ThreadMessage = components["schemas"]["Message"];
export type DecisionReason = components["schemas"]["DecisionReason"];
export type QuestionTemplate = components["schemas"]["QuestionTemplate"];
export type TeamMember = components["schemas"]["Assignment"];

export interface TransitionInput {
  to_status: string;
  reason_code?: string;
  reason_text?: string;
  lock_version?: number;
}

export const atsKeys = {
  notes: (orgId: string, id: string) => ["hr-applications", orgId, id, "notes"] as const,
  clarifications: (orgId: string, id: string) =>
    ["hr-applications", orgId, id, "clarifications"] as const,
  messages: (orgId: string, id: string) => ["hr-applications", orgId, id, "messages"] as const,
  reasons: (orgId: string, appliesTo: string) => ["hr-decision-reasons", orgId, appliesTo] as const,
  templates: (orgId: string) => ["hr-clarification-templates", orgId] as const,
  team: (orgId: string, jobId: string) => ["jobs", orgId, jobId, "assignments"] as const,
};

/** Staff ATS calls; every one carries the organisation context (`X-Org-Id`). */
export function atsApi(orgId: string) {
  const o = { orgId };
  const base = (id: string) => `/hr/applications/${id}`;
  return {
    transition: (id: string, body: TransitionInput) =>
      api.post<HRApplicationDetail>(`${base(id)}/transition/`, body, o),
    notes: (id: string) => api.get<Note[]>(`${base(id)}/notes/`, o),
    addNote: (id: string, body: { body: string; mentions: string[]; visibility: string }) =>
      api.post<Note>(`${base(id)}/notes/`, body, o),
    setTags: (id: string, tags: string[]) =>
      api.put<HRApplicationDetail>(`${base(id)}/tags/`, { tags }, o),
    assign: (id: string, userId: string | null) =>
      api.post<HRApplicationDetail>(`${base(id)}/assign/`, { user_id: userId }, o),
    reasons: (appliesTo: string) =>
      api.get<DecisionReason[]>("/hr/decision-reasons/", {
        ...o,
        query: { applies_to: appliesTo },
      }),
    clarifications: (id: string) => api.get<Clarification[]>(`${base(id)}/clarifications/`, o),
    askClarification: (
      id: string,
      body: {
        questions: { prompt: string; allow_upload: boolean }[];
        due_at: string;
        message: string;
      },
    ) => api.post<Clarification>(`${base(id)}/clarifications/`, body, o),
    cancelClarification: (id: string, cid: string) =>
      api.post<Clarification>(`${base(id)}/clarifications/${cid}/cancel/`, undefined, o),
    templates: () => api.get<QuestionTemplate[]>("/hr/clarification-templates/", o),
    messages: (id: string) => api.get<ThreadMessage[]>(`${base(id)}/messages/`, o),
    sendMessage: (id: string, body: string) =>
      api.post<ThreadMessage>(`${base(id)}/messages/`, { body, attachment_ids: [] }, o),
    team: (jobId: string) => api.get<TeamMember[]>(`/hr/jobs/${jobId}/assignments/`, o),
  };
}

/** Reason list a move needs (mirrors backend `ats.REASON_LIST` + reopen = override). */
export const TERMINAL = ["not_selected", "withdrawn", "hired", "offer_declined", "abandoned"];
export function reasonListFor(from: string, to: string): string | null {
  if (TERMINAL.includes(from) && to === "under_review") return "override";
  return (
    (
      { shortlisted: "shortlist", not_selected: "not_selected", on_hold: "hold" } as Record<
        string,
        string
      >
    )[to] ?? null
  );
}

/** Kanban columns (statuses HR works with); drafts are never shown to staff. */
export const PIPELINE_COLUMNS = [
  "submitted",
  "processing",
  "processing_error",
  "needs_information",
  "under_review",
  "on_hold",
  "shortlisted",
  "interview",
  "offer",
  "hired",
  "not_selected",
  "withdrawn",
] as const;
