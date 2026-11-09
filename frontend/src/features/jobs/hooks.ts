"use client";

import { useQuery } from "@tanstack/react-query";

import { useActiveMembership } from "@/features/organisations/hooks";

import { jobsApi, type JobListParams } from "./api";

/**
 * Mirrors backend `rbac.ORG_ACTIONS` for the job actions, for UI *hiding only*.
 * The server answers 403 for anything not allowed.
 */
const JOB_ACTIONS = {
  "jobs.view": ["org_admin", "hr_manager", "recruiter", "hiring_manager", "auditor"],
  "jobs.create": ["org_admin", "hr_manager", "recruiter"],
  "jobs.approve": ["org_admin", "hr_manager"],
  "jobs.publish": ["org_admin", "hr_manager"],
  "jobs.assign": ["org_admin", "hr_manager"],
  "questions.protected_exception": ["org_admin", "hr_manager"],
} as const;

export type JobUiAction = keyof typeof JOB_ACTIONS;

export function canJob(role: string | null | undefined, action: JobUiAction): boolean {
  return !!role && (JOB_ACTIONS[action] as readonly string[]).includes(role);
}

export function useJobsContext() {
  const { membership, isPending } = useActiveMembership();
  const orgId = membership?.organisation_id ?? null;
  return {
    orgId,
    role: membership?.role ?? null,
    isPending,
    api: orgId ? jobsApi(orgId) : null,
  };
}

export const jobKeys = {
  all: (orgId: string) => ["jobs", orgId] as const,
  list: (orgId: string, params: JobListParams) => ["jobs", orgId, "list", params] as const,
  detail: (orgId: string, id: string) => ["jobs", orgId, id] as const,
  readiness: (orgId: string, id: string, stage: string) =>
    ["jobs", orgId, id, "readiness", stage] as const,
  events: (orgId: string, id: string) => ["jobs", orgId, id, "events"] as const,
  versions: (orgId: string, id: string) => ["jobs", orgId, id, "versions"] as const,
  assignments: (orgId: string, id: string) => ["jobs", orgId, id, "assignments"] as const,
};

export function useJobs(params: JobListParams) {
  const { orgId, api } = useJobsContext();
  return useQuery({
    queryKey: jobKeys.list(orgId ?? "", params),
    queryFn: () => api!.list(params),
    enabled: !!api,
    placeholderData: (prev) => prev,
  });
}

export function useJob(id: string | undefined) {
  const { orgId, api } = useJobsContext();
  return useQuery({
    queryKey: jobKeys.detail(orgId ?? "", id ?? ""),
    queryFn: () => api!.get(id!),
    enabled: !!api && !!id,
  });
}

export function useReadiness(id: string | undefined, stage: "submit" | "publish", enabled = true) {
  const { orgId, api } = useJobsContext();
  return useQuery({
    queryKey: jobKeys.readiness(orgId ?? "", id ?? "", stage),
    queryFn: () => api!.lint(id!, stage),
    enabled: !!api && !!id && enabled,
  });
}

export function useJobEvents(id: string) {
  const { orgId, api } = useJobsContext();
  return useQuery({
    queryKey: jobKeys.events(orgId ?? "", id),
    queryFn: () => api!.events(id),
    enabled: !!api,
  });
}

export function useJobVersions(id: string) {
  const { orgId, api } = useJobsContext();
  return useQuery({
    queryKey: jobKeys.versions(orgId ?? "", id),
    queryFn: () => api!.versions(id),
    enabled: !!api,
  });
}

export function useJobAssignments(id: string) {
  const { orgId, api } = useJobsContext();
  return useQuery({
    queryKey: jobKeys.assignments(orgId ?? "", id),
    queryFn: () => api!.assignments(id),
    enabled: !!api,
  });
}
