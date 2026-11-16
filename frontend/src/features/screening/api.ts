"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

export type ScreeningRun = components["schemas"]["ScreeningRun"];
export type ScreeningRunDetail = components["schemas"]["ScreeningRunDetail"];
export type ScreeningAnalytics = components["schemas"]["ScreeningAnalytics"];
export type Evaluation = components["schemas"]["Evaluation"];
export type CriterionResult = components["schemas"]["CriterionResult"];
export type StartRunInput = components["schemas"]["StartRunRequest"];
export type VerifyInput = components["schemas"]["VerifyRequest"];
export type Verification = components["schemas"]["Verification"];
export type EvaluationSummary = components["schemas"]["EvaluationSummary"];

/** Mirrors backend RBAC (`applications.transition`) — UI hiding only; the server decides. */
export const SCREENING_EDITORS = ["org_admin", "hr_manager", "recruiter"];

export const BANDS = [
  "recommended_for_review",
  "review_needed",
  "eligibility_review",
  "lower_match",
  "manual_review_requested",
] as const;

const ACTIVE = new Set(["queued", "running"]);

export const screeningKeys = {
  runs: (orgId: string, jobId: string) => ["screening", orgId, "job", jobId, "runs"] as const,
  analytics: (orgId: string, jobId: string) =>
    ["screening", orgId, "job", jobId, "analytics"] as const,
  evaluation: (orgId: string, appId: string) =>
    ["hr-applications", orgId, appId, "evaluation"] as const,
};

export function useScreeningRuns(jobId: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: screeningKeys.runs(orgId ?? "", jobId),
    queryFn: () => api.get<ScreeningRun[]>(`/hr/jobs/${jobId}/screening-runs/`, { orgId: orgId! }),
    enabled: !!orgId,
    refetchInterval: (q) => (q.state.data?.some((r) => ACTIVE.has(r.status)) ? 3000 : false),
  });
}

export function useScreeningAnalytics(jobId: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: screeningKeys.analytics(orgId ?? "", jobId),
    queryFn: () =>
      api.get<ScreeningAnalytics>(`/hr/jobs/${jobId}/screening-analytics/`, { orgId: orgId! }),
    enabled: !!orgId,
  });
}

export function useRunFailures(runId: string | null) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: ["screening", orgId ?? "", "run", runId],
    queryFn: () => api.get<ScreeningRunDetail>(`/hr/screening-runs/${runId}/`, { orgId: orgId! }),
    enabled: !!orgId && !!runId,
  });
}

export function useStartRun(jobId: string) {
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<StartRunInput>) =>
      api.post<ScreeningRunDetail>(`/hr/jobs/${jobId}/screening-runs/`, body, { orgId: orgId! }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["screening", orgId ?? "", "job", jobId] });
    },
  });
}

/** The current evaluation, or `null` while the application has not been evaluated (404). */
export function useEvaluation(appId: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: screeningKeys.evaluation(orgId ?? "", appId),
    queryFn: async () => {
      try {
        return await api.get<Evaluation>(`/hr/applications/${appId}/evaluation/`, {
          orgId: orgId!,
        });
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
    enabled: !!orgId,
  });
}

export function useVerifyClaim(appId: string) {
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, ...body }: Partial<VerifyInput> & { claimId: string }) =>
      api.post<Verification>(`/hr/claims/${claimId}/verify/`, body, { orgId: orgId! }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: screeningKeys.evaluation(orgId ?? "", appId) });
    },
  });
}

export function useEvaluationVersions(appId: string) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: [...screeningKeys.evaluation(orgId ?? "", appId), "versions"],
    queryFn: () =>
      api.get<EvaluationSummary[]>(`/hr/applications/${appId}/evaluations/`, { orgId: orgId! }),
    enabled: !!orgId,
  });
}

export function useEvaluationVersion(appId: string, version: number | null) {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: [...screeningKeys.evaluation(orgId ?? "", appId), "version", version],
    queryFn: () =>
      api.get<Evaluation>(`/hr/applications/${appId}/evaluations/${version}/`, {
        orgId: orgId!,
      }),
    enabled: !!orgId && version !== null,
  });
}
