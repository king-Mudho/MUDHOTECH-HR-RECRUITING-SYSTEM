import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

type S = components["schemas"];
export type JobListItem = S["HRJobList"];
export type JobDetail = S["HRJobDetail"];
export type JobStatus = S["JobStatusEnum"];
export type JobWrite = S["JobWriteRequest"];
export type JobPatch = S["PatchedJobPatchRequest"];
export type CriterionInput = S["CriterionInputRequest"];
export type Criterion = S["Criterion"];
export type RubricCategory = S["RubricCategoryRequest"];
export type QuestionInput = S["QuestionInputRequest"];
export type QuestionOut = S["QuestionOut"];
export type Readiness = S["Readiness"];
export type Assignment = S["Assignment"];
export type JobEvent = S["JobEvent"];
export type VersionSummary = S["VersionSummary"];
export type Suggestions = S["Suggestions"];
export type Skill = S["Skill"];
export type Paginated<T> = {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
};

export interface JobListParams {
  status?: string;
  search?: string;
  assigned?: "me";
  ordering?: string;
  page?: number;
}

const base = "/hr/jobs";
const job = (id: string) => `${base}/${id}`;

/** HR vacancy API (docs/04 Jobs). Every call carries the organisation context (`X-Org-Id`). */
export function jobsApi(orgId: string) {
  const o = { orgId };
  return {
    list: (params: JobListParams = {}) =>
      api.get<Paginated<JobListItem>>(`${base}/`, { ...o, query: { ...params } }),
    get: (id: string) => api.get<JobDetail>(`${job(id)}/`, o),
    create: (data: JobWrite) => api.post<JobDetail>(`${base}/`, data, o),
    update: (id: string, data: JobPatch & { lock_version: number }) =>
      api.patch<JobDetail>(`${job(id)}/`, data, o),
    setCriteria: (id: string, criteria: CriterionInput[], lockVersion?: number) =>
      api.put<JobDetail>(`${job(id)}/criteria/`, { criteria, lock_version: lockVersion }, o),
    setRubric: (id: string, categories: RubricCategory[], lockVersion?: number) =>
      api.put<JobDetail>(`${job(id)}/rubric/`, { categories, lock_version: lockVersion }, o),
    setQuestionnaire: (id: string, questions: QuestionInput[], lockVersion?: number) =>
      api.put<JobDetail>(`${job(id)}/questionnaire/`, { questions, lock_version: lockVersion }, o),
    lint: (id: string, stage: "submit" | "publish") =>
      api.post<Readiness>(`${job(id)}/lint/`, undefined, { ...o, query: { stage } }),
    suggestions: (id: string) => api.post<Suggestions>(`${job(id)}/ai-suggestions/`, undefined, o),
    protectedException: (id: string, key: string, reason: string) =>
      api.post<QuestionOut>(
        `${job(id)}/questions/${encodeURIComponent(key)}/protected-exception/`,
        { reason },
        o,
      ),
    action: (id: string, action: JobAction, body: Record<string, unknown> = {}) =>
      api.post<JobDetail>(`${job(id)}/${action}/`, body, o),
    assignments: (id: string) => api.get<Assignment[]>(`${job(id)}/assignments/`, o),
    setAssignments: (
      id: string,
      assignments: { membership_id: string; role_on_job: Assignment["role_on_job"] }[],
    ) => api.put<Assignment[]>(`${job(id)}/assignments/`, { assignments }, o),
    events: (id: string) => api.get<JobEvent[]>(`${job(id)}/events/`, o),
    versions: (id: string) => api.get<VersionSummary[]>(`${job(id)}/versions/`, o),
    skills: (search: string) =>
      api.get<Skill[]>("/taxonomy/skills/", { ...o, query: { search, limit: 10 } }),
  };
}

export type JobAction =
  | "submit-for-approval"
  | "approve"
  | "reject"
  | "publish"
  | "schedule"
  | "pause"
  | "resume"
  | "close"
  | "archive"
  | "extend-deadline"
  | "duplicate"
  | "new-version";
