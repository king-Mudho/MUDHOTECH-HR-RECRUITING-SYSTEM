"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

import { candidateApi, type SectionName } from "./api";

export type Resume = components["schemas"]["Resume"];
export type TimelineEntry = components["schemas"]["TimelineEntry"];

export const candidateKeys = {
  profile: ["candidate", "profile"] as const,
  section: (name: SectionName) => ["candidate", "profile", name] as const,
  resumes: ["candidate", "resumes"] as const,
  applications: ["candidate", "applications"] as const,
  application: (id: string) => ["candidate", "applications", id] as const,
  review: (id: string) => ["candidate", "applications", id, "review"] as const,
  timeline: (id: string) => ["candidate", "applications", id, "timeline"] as const,
};

export function useProfile() {
  return useQuery({ queryKey: candidateKeys.profile, queryFn: candidateApi.profile });
}

export function useSection<T>(name: SectionName) {
  return useQuery({
    queryKey: candidateKeys.section(name),
    queryFn: () => candidateApi.list<T>(name),
  });
}

export function useResumes() {
  return useQuery({
    queryKey: candidateKeys.resumes,
    queryFn: () => api.get<Resume[]>("/candidate/resumes/"),
  });
}

export function useApplications() {
  return useQuery({ queryKey: candidateKeys.applications, queryFn: candidateApi.applications });
}

export function useApplication(id: string) {
  return useQuery({
    queryKey: candidateKeys.application(id),
    queryFn: () => candidateApi.application(id),
  });
}

export function useReview(id: string, enabled = true) {
  return useQuery({
    queryKey: candidateKeys.review(id),
    queryFn: () => candidateApi.review(id),
    enabled,
  });
}

export function useTimeline(id: string) {
  return useQuery({
    queryKey: candidateKeys.timeline(id),
    queryFn: () => api.get<TimelineEntry[]>(`/applications/${id}/timeline/`),
  });
}
