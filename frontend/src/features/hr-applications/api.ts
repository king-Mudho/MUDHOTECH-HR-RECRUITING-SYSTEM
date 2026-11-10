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
