import { z } from "zod";

import type { CriterionInput, JobDetail, QuestionInput, RubricCategory } from "./api";

// ------------------------------------------------------------------------------ details
export const EMPLOYMENT_TYPES = [
  "full_time",
  "part_time",
  "contract",
  "internship",
  "attachment",
  "temporary",
  "graduate_trainee",
] as const;
export const WORKPLACE_TYPES = ["on_site", "hybrid", "remote"] as const;
export const SENIORITIES = [
  "",
  "entry",
  "junior",
  "mid",
  "senior",
  "lead",
  "manager",
  "executive",
] as const;
export const DOCUMENT_TYPES = [
  "cv",
  "cover_letter",
  "certificates",
  "transcripts",
  "id_document",
  "professional_registration",
  "portfolio",
  "references",
] as const;

const money = z
  .string()
  .trim()
  .refine((v) => v === "" || /^\d{1,10}(\.\d{1,2})?$/.test(v), "invalidAmount");

export const detailsSchema = z
  .object({
    title: z.string().trim().min(2, "required").max(200),
    reference_code: z.string().trim().max(50),
    department_id: z.string(),
    location_ids: z.array(z.string()),
    workplace_type: z.enum(WORKPLACE_TYPES),
    employment_type: z.enum(EMPLOYMENT_TYPES),
    seniority: z.enum(SENIORITIES),
    openings: z.number({ error: "required" }).int().min(1, "outOfRange").max(1000, "outOfRange"),
    closes_at_local: z.string(),
    timezone: z.string().min(1, "required"),
    salary_min: money,
    salary_max: money,
    salary_currency: z.enum(["USD", "ZWG"]),
    salary_period: z.enum(["hour", "day", "month", "year"]),
    salary_disclosed: z.boolean(),
    visibility: z.enum(["public", "unlisted"]),
    summary: z.string().max(2000),
    responsibilities_html: z.string().max(20000),
    requirements_html: z.string().max(20000),
    benefits_html: z.string().max(20000),
    required_documents: z.array(z.enum(DOCUMENT_TYPES)),
  })
  .refine(
    (v) =>
      v.salary_min === "" || v.salary_max === "" || Number(v.salary_min) <= Number(v.salary_max),
    { message: "salaryRange", path: ["salary_max"] },
  );

export type DetailsValues = z.infer<typeof detailsSchema>;

export function detailsFromJob(
  job: JobDetail | undefined,
  toLocal: (iso: string | null, tz: string) => string,
): DetailsValues {
  const v = job?.version;
  return {
    title: job?.title ?? "",
    reference_code: job?.reference_code ?? "",
    department_id: job?.department ?? "",
    location_ids: [...(job?.locations ?? [])],
    workplace_type: job?.workplace_type ?? "on_site",
    employment_type: job?.employment_type ?? "full_time",
    seniority: (job?.seniority ?? "") as DetailsValues["seniority"],
    openings: job?.openings ?? 1,
    closes_at_local: job ? toLocal(job.closes_at, job.timezone) : "",
    timezone: job?.timezone ?? "Africa/Harare",
    salary_min: job?.salary_min ?? "",
    salary_max: job?.salary_max ?? "",
    salary_currency: job?.salary_currency ?? "USD",
    salary_period: job?.salary_period ?? "month",
    salary_disclosed: job?.salary_disclosed ?? false,
    visibility: job?.visibility ?? "public",
    summary: v?.summary ?? "",
    responsibilities_html: v?.responsibilities_html ?? "",
    requirements_html: v?.requirements_html ?? "",
    benefits_html: v?.benefits_html ?? "",
    required_documents: ((v?.required_documents as string[] | undefined) ?? ["cv"]).filter(
      (d): d is (typeof DOCUMENT_TYPES)[number] =>
        (DOCUMENT_TYPES as readonly string[]).includes(d),
    ),
  };
}

// ----------------------------------------------------------------------------- criteria
export const CRITERION_TYPES = [
  "skill",
  "experience",
  "qualification",
  "certification",
  "competency",
  "language",
  "licence",
  "eligibility",
] as const;
export const RUBRIC_KEYS = [
  "technical",
  "experience",
  "competency",
  "qualification",
  "answers",
] as const;

export const criterionSchema = z
  .object({
    type: z.enum(CRITERION_TYPES),
    importance: z.enum(["essential", "preferred"]),
    title: z.string().trim().min(1, "required").max(200),
    description: z.string().max(2000),
    justification: z.string().max(2000),
    skill_id: z.string().nullable(),
    min_months: z.number().int().min(0, "outOfRange").max(600, "outOfRange").nullable(),
    equivalents: z.array(z.string().trim().min(1).max(200)).max(20),
    rubric_category: z.enum(RUBRIC_KEYS),
  })
  .refine((c) => c.importance !== "essential" || c.justification.trim().length > 0, {
    message: "justificationRequired",
    path: ["justification"],
  });

export type CriterionValues = z.infer<typeof criterionSchema>;
export const criteriaFormSchema = z.object({ criteria: z.array(criterionSchema).max(40) });
export type CriteriaFormValues = z.infer<typeof criteriaFormSchema>;

const DEFAULT_CATEGORY: Record<(typeof CRITERION_TYPES)[number], (typeof RUBRIC_KEYS)[number]> = {
  skill: "technical",
  experience: "experience",
  competency: "competency",
  qualification: "qualification",
  certification: "qualification",
  licence: "qualification",
  language: "competency",
  eligibility: "answers",
};

export function defaultCategory(type: (typeof CRITERION_TYPES)[number]) {
  return DEFAULT_CATEGORY[type];
}

export function emptyCriterion(): CriterionValues {
  return {
    type: "skill",
    importance: "preferred",
    title: "",
    description: "",
    justification: "",
    skill_id: null,
    min_months: null,
    equivalents: [],
    rubric_category: "technical",
  };
}

export function criteriaFromJob(job: JobDetail | undefined): CriterionValues[] {
  return (job?.criteria ?? []).map((c) => ({
    type: c.type,
    importance: c.importance,
    title: c.title,
    description: c.description,
    justification: c.justification,
    skill_id: c.skill,
    min_months: c.min_months,
    equivalents: Array.isArray(c.equivalents) ? (c.equivalents as string[]) : [],
    rubric_category: c.rubric_category,
  }));
}

export function criteriaToInput(values: CriterionValues[]): CriterionInput[] {
  return values.map((c) => ({ ...c, skill_id: c.skill_id || null }));
}

// ------------------------------------------------------------------------------- rubric
export interface RubricBand {
  score: number;
  descriptor: string;
}
export interface RubricRow {
  key: (typeof RUBRIC_KEYS)[number];
  label: string;
  weight: number;
  bands: RubricBand[];
}

export function rubricTotal(rows: Pick<RubricRow, "weight">[]): number {
  return rows.reduce((sum, r) => sum + (Number.isFinite(r.weight) ? r.weight : 0), 0);
}

/** Client-side mirror of the server rubric rules (EC-JOB-02); the server re-validates. */
export function rubricProblems(rows: RubricRow[]): string[] {
  const problems: string[] = [];
  if (rubricTotal(rows) !== 100) problems.push("rubricTotal");
  for (const r of rows) {
    const scores = r.bands.map((b) => b.score);
    if (r.bands.length < 2 || r.bands.some((b) => !b.descriptor.trim()))
      problems.push("rubricBands");
    else if (scores.some((s, i) => i > 0 && s <= scores[i - 1]!)) problems.push("rubricBandOrder");
  }
  return [...new Set(problems)];
}

export function rubricFromJob(job: JobDetail | undefined): RubricRow[] {
  return ((job?.rubric?.categories ?? []) as RubricCategory[]).map((c) => ({
    key: c.key as RubricRow["key"],
    label: c.label ?? c.key,
    weight: c.weight,
    bands: c.bands.map((b) => ({ score: b.score, descriptor: b.descriptor })),
  }));
}

// ---------------------------------------------------------------------------- questions
export const QUESTION_TYPES = [
  "yes_no",
  "single_choice",
  "multiple_choice",
  "number",
  "short_text",
  "long_text",
  "date",
  "file_upload",
  "scale",
  "availability",
  "salary_expectation",
] as const;
export type QuestionType = (typeof QUESTION_TYPES)[number];
export const CHOICE_TYPES: readonly QuestionType[] = ["single_choice", "multiple_choice"];

/** Scoring modes allowed per type (mirrors backend questionnaires/validation.py). */
export const MODES_BY_TYPE: Record<QuestionType, readonly string[]> = {
  yes_no: ["none", "exact", "human"],
  single_choice: ["none", "exact", "options", "human"],
  multiple_choice: ["none", "options", "human"],
  number: ["none", "range", "exact", "human"],
  scale: ["none", "range", "exact", "human"],
  short_text: ["none", "rubric_text", "human"],
  long_text: ["none", "rubric_text", "human"],
  date: ["none", "human"],
  file_upload: ["none", "human"],
  availability: ["none", "range", "human"],
  salary_expectation: ["none"],
};

export interface QuestionOption {
  label: string;
  value: string;
  points: string;
}

export interface QuestionValues {
  key: string;
  type: QuestionType;
  prompt: string;
  help_text: string;
  required: boolean;
  options: QuestionOption[];
  scoring_mode: string;
  expected: string;
  keywords: string;
  is_knockout: boolean;
  knockout_expected: string;
  show_if_question: string;
  show_if_value: string;
  protected_topic_flag: { topic: string; explanation?: string }[];
  protected_exception_reason: string;
  /** Settings the builder does not edit yet (numeric bands, min/max, word limits) round-trip. */
  scoring_raw: Record<string, unknown>;
  config_raw: Record<string, unknown>;
}

export function slugKey(text: string, taken: Set<string>): string {
  const base =
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40) || "question";
  let key = base;
  let n = 2;
  while (taken.has(key)) key = `${base}-${n++}`;
  return key;
}

export function emptyQuestion(taken: Set<string>): QuestionValues {
  return {
    key: slugKey("question", taken),
    type: "yes_no",
    prompt: "",
    help_text: "",
    required: true,
    options: [],
    scoring_mode: "none",
    expected: "",
    keywords: "",
    is_knockout: false,
    knockout_expected: "",
    show_if_question: "",
    show_if_value: "",
    protected_topic_flag: [],
    protected_exception_reason: "",
    scoring_raw: {},
    config_raw: {},
  };
}

export function questionsFromJob(job: JobDetail | undefined): QuestionValues[] {
  return (job?.questions ?? []).map((q) => {
    const scoring = (q.scoring ?? {}) as Record<string, unknown>;
    const showIf = ((q.branching ?? {}) as { show_if?: { question?: string; value?: unknown } })
      .show_if;
    return {
      key: q.key,
      type: q.type as QuestionType,
      prompt: q.prompt,
      help_text: q.help_text,
      required: q.required,
      options: q.options.map((o) => ({ label: o.label, value: o.value, points: o.points ?? "" })),
      scoring_mode: String(scoring.mode ?? "none"),
      expected: scoring.expected == null ? "" : String(scoring.expected),
      keywords: Array.isArray(scoring.keywords) ? (scoring.keywords as string[]).join(", ") : "",
      is_knockout: q.is_knockout,
      knockout_expected: q.knockout_expected == null ? "" : String(q.knockout_expected),
      show_if_question: showIf?.question ?? "",
      show_if_value: showIf?.value == null ? "" : String(showIf.value),
      protected_topic_flag: (q.protected_topic_flag ??
        []) as QuestionValues["protected_topic_flag"],
      protected_exception_reason: q.protected_exception_reason,
      scoring_raw: scoring,
      config_raw: (q.config ?? {}) as Record<string, unknown>,
    };
  });
}

export function questionsToInput(values: QuestionValues[]): QuestionInput[] {
  return values.map((q) => {
    const scoring: Record<string, unknown> =
      q.scoring_mode === q.scoring_raw.mode ? { ...q.scoring_raw } : { mode: q.scoring_mode };
    if (q.scoring_mode === "exact") scoring.expected = q.expected;
    if (q.scoring_mode === "rubric_text")
      scoring.keywords = q.keywords
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
    const out: QuestionInput = {
      key: q.key,
      type: q.type,
      prompt: q.prompt,
      help_text: q.help_text,
      required: q.required,
      config: q.config_raw,
      scoring,
      is_knockout: q.is_knockout,
      knockout_expected: q.is_knockout ? q.knockout_expected : null,
      branching: q.show_if_question
        ? { show_if: { question: q.show_if_question, op: "eq", value: q.show_if_value } }
        : {},
      options: CHOICE_TYPES.includes(q.type)
        ? q.options.map((o) => ({ label: o.label, value: o.value, points: o.points || null }))
        : [],
    };
    return out;
  });
}

export function optionValuesFor(q: Pick<QuestionValues, "type" | "options">): string[] {
  if (q.type === "yes_no") return ["yes", "no"];
  return q.options.map((o) => o.value);
}
