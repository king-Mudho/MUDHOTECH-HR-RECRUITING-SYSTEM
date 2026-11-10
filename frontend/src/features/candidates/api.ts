import { api, newIdempotencyKey } from "@/lib/api-client";
import type { components } from "@/types/api";

type S = components["schemas"];
export type Profile = S["Profile"];
export type ProfilePatch = S["PatchedProfileRequest"];
export type Experience = S["Experience"];
export type Education = S["Education"];
export type Certification = S["Certification"];
export type CandidateSkill = S["CandidateSkill"];
export type Language = S["Language"];
export type Application = S["Application"];
export type Review = S["Review"];
export type MissingItem = S["MissingItem"];

export type SectionName = "experiences" | "educations" | "certifications" | "skills" | "languages";

const profile = "/candidate/profile";

export const candidateApi = {
  profile: () => api.get<Profile>(`${profile}/`),
  updateProfile: (data: ProfilePatch) => api.patch<Profile>(`${profile}/`, data),
  list: <T>(section: SectionName) => api.get<T[]>(`${profile}/${section}/`),
  create: <T>(section: SectionName, data: Record<string, unknown>) =>
    api.post<T>(`${profile}/${section}/`, data),
  update: <T>(section: SectionName, id: string, data: Record<string, unknown>) =>
    api.patch<T>(`${profile}/${section}/${id}/`, data),
  remove: (section: SectionName, id: string) => api.delete<void>(`${profile}/${section}/${id}/`),

  applications: () => api.get<Application[]>("/applications/"),
  application: (id: string) => api.get<Application>(`/applications/${id}/`),
  start: (jobId: string, source?: Record<string, string>) =>
    api.post<Application>("/applications/", { job_id: jobId, source }),
  updateDraft: (
    id: string,
    data: { lock_version: number; last_step?: number; contact?: Record<string, string> },
  ) => api.patch<Application>(`/applications/${id}/`, data),
  setDocuments: (
    id: string,
    documents: { document_id: string; role: string; required_doc_key?: string }[],
  ) => api.put<Review>(`/applications/${id}/documents/`, { documents }),
  setAnswers: (id: string, answers: { key: string; value: unknown }[]) =>
    api.put<Review>(`/applications/${id}/answers/`, { answers }),
  review: (id: string) => api.get<Review>(`/applications/${id}/review/`),
  submit: (
    id: string,
    body: { accept_privacy: boolean; objects_to_automated_processing: boolean },
    idempotencyKey: string = newIdempotencyKey(),
  ) =>
    api.post<{ id: string; reference: string; submitted_at: string; status: string }>(
      `/applications/${id}/submit/`,
      body,
      { idempotencyKey },
    ),
  withdraw: (id: string, reason: string) =>
    api.post<Application>(`/applications/${id}/withdraw/`, { reason }),
};
