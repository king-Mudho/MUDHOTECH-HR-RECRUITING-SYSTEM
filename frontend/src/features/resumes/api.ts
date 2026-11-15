import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

type S = components["schemas"];
export type ResumeExtraction = S["ResumeExtraction"];
export type ClaimView = S["ClaimView"];
export type ApplicationExtraction = S["ApplicationExtraction"];
export type ApplicationClaim = S["ApplicationClaim"];
export type ImportResult = S["ImportResult"];

export const resumeKeys = {
  preview: (documentId: string) => ["resumes", "preview", documentId] as const,
  application: (applicationId: string) => ["resumes", "application", applicationId] as const,
};

export const resumesApi = {
  preview: (documentId: string) =>
    api.get<ResumeExtraction>(`/candidate/resumes/${documentId}/extraction/`),
  importToProfile: (documentId: string, indexes: number[]) =>
    api.post<ImportResult>(`/candidate/resumes/${documentId}/import-to-profile/`, {
      confirm: true,
      indexes,
    }),
  application: (applicationId: string) =>
    api.get<ApplicationExtraction>(`/candidate/applications/${applicationId}/extraction/`),
  correct: (
    claimId: string,
    body: { values: Record<string, string>; remove: boolean; note: string },
  ) => api.post(`/candidate/claims/${claimId}/corrections/`, body),
};

const READING = new Set(["pending", "running"]);

/** The candidate's CV preview; polls every 2 s while the CV is still being read (max ~2 min). */
export function useResumePreview(documentId: string | null | undefined) {
  return useQuery({
    queryKey: resumeKeys.preview(documentId ?? ""),
    queryFn: () => resumesApi.preview(documentId!),
    enabled: !!documentId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || !READING.has(data.status)) return false;
      return query.state.dataUpdateCount > 60 ? false : 2000;
    },
  });
}

export function useApplicationExtraction(applicationId: string) {
  return useQuery({
    queryKey: resumeKeys.application(applicationId),
    queryFn: () => resumesApi.application(applicationId),
  });
}

export const GROUPS = [
  "experience",
  "education",
  "certification",
  "skill",
  "language",
  "project",
] as const;
export type Group = (typeof GROUPS)[number];

export function grouped<T extends ClaimView>(claims: T[]) {
  const used = claims.filter((c) => !c.excluded);
  const byType = Object.fromEntries(
    GROUPS.map((g) => [g, used.filter((c) => c.type === g)]),
  ) as Record<Group, T[]>;
  const summary = used.find((c) => c.type === "summary");
  const ignored = claims.filter((c) => c.excluded);
  return { byType, summary, ignored };
}
