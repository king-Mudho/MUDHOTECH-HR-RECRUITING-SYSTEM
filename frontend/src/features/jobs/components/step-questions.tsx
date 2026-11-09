"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useFieldArray, useForm, useWatch, type UseFormReturn } from "react-hook-form";
import { z } from "zod";

import { ErrorSummary, SelectField, useErrorText } from "@/components/forms/form-field";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";

import { canJob, jobKeys, useJobsContext } from "../hooks";
import {
  CHOICE_TYPES,
  MODES_BY_TYPE,
  QUESTION_TYPES,
  emptyQuestion,
  optionValuesFor,
  questionsFromJob,
  questionsToInput,
  slugKey,
  type QuestionType,
  type QuestionValues,
} from "../schemas";
import { useAutosave } from "./use-autosave";
import { StepFooter, useWizard } from "./wizard-context";

const questionSchema = z
  .object({
    key: z.string().regex(/^[a-z0-9][a-z0-9_-]{0,59}$/, "invalidKey"),
    type: z.enum(QUESTION_TYPES),
    prompt: z.string().trim().min(1, "required").max(1000),
    help_text: z.string().max(1000),
    required: z.boolean(),
    options: z.array(
      z.object({
        label: z.string().trim().min(1, "required"),
        value: z.string(),
        points: z.string(),
      }),
    ),
    scoring_mode: z.string(),
    expected: z.string(),
    keywords: z.string(),
    is_knockout: z.boolean(),
    knockout_expected: z.string(),
    show_if_question: z.string(),
    show_if_value: z.string(),
    protected_topic_flag: z.array(
      z.object({ topic: z.string(), explanation: z.string().optional() }).passthrough(),
    ),
    protected_exception_reason: z.string(),
    scoring_raw: z.record(z.string(), z.unknown()),
    config_raw: z.record(z.string(), z.unknown()),
  })
  .superRefine((q, ctx) => {
    if (CHOICE_TYPES.includes(q.type) && q.options.length < 2)
      ctx.addIssue({ code: "custom", path: ["options"], message: "twoOptions" });
    if (q.scoring_mode === "exact" && !q.expected)
      ctx.addIssue({ code: "custom", path: ["expected"], message: "required" });
    if (q.scoring_mode === "rubric_text" && !q.keywords.trim())
      ctx.addIssue({ code: "custom", path: ["keywords"], message: "required" });
    if (q.is_knockout && !q.knockout_expected)
      ctx.addIssue({ code: "custom", path: ["knockout_expected"], message: "required" });
  });
const formSchema = z.object({ questions: z.array(questionSchema).max(60) });
type FormValues = { questions: QuestionValues[] };

const BANK: { key: string; type: QuestionType; options?: string[] }[] = [
  { key: "right_to_work", type: "yes_no" },
  { key: "notice_period", type: "availability" },
  { key: "drivers_licence", type: "yes_no" },
  { key: "professional_registration", type: "yes_no" },
  { key: "portfolio", type: "yes_no" },
  { key: "relocate", type: "yes_no" },
  { key: "years_experience", type: "number" },
  { key: "motivation", type: "long_text" },
];

function ProtectedTopicNotice({ q, index }: { q: QuestionValues; index: number }) {
  const t = useTranslations("jobs.questions.protected");
  const { api, job, role } = useWizard();
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const [reason, setReason] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  if (q.protected_topic_flag.length === 0) return null;
  const justified = !!q.protected_exception_reason.trim() || state === "done";
  const record = async () => {
    setState("saving");
    setError(null);
    try {
      await api.protectedException(job.id, q.key, reason);
      setState("done");
      await client.invalidateQueries({ queryKey: jobKeys.detail(orgId!, job.id) });
    } catch (err) {
      setState("error");
      setError(err instanceof ApiError ? err.message : t("error"));
    }
  };
  return (
    <Alert variant={justified ? "default" : "destructive"} role="status">
      <ShieldAlert aria-hidden="true" />
      <AlertTitle>{justified ? t("justifiedTitle") : t("title")}</AlertTitle>
      <AlertDescription className="flex flex-col gap-2">
        <ul className="list-disc pl-5">
          {q.protected_topic_flag.map((f, i) => (
            <li key={`${f.topic}-${i}`}>{f.explanation ?? f.topic}</li>
          ))}
        </ul>
        {justified ? (
          <p>{t("justified", { reason: q.protected_exception_reason || reason })}</p>
        ) : canJob(role, "questions.protected_exception") ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`exception-${index}`}>{t("reasonLabel")}</Label>
            <textarea
              id={`exception-${index}`}
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="border-input bg-background rounded-md border px-3 py-2 text-sm"
            />
            <div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={reason.trim().length < 20 || state === "saving"}
                onClick={() => void record()}
              >
                {t("record")}
              </Button>
            </div>
            {error ? <p role="alert">{error}</p> : null}
          </div>
        ) : (
          <p>{t("askManager")}</p>
        )}
      </AlertDescription>
    </Alert>
  );
}

function QuestionCard({
  index,
  total,
  form,
  onRemove,
  onMove,
}: {
  index: number;
  total: number;
  form: UseFormReturn<FormValues>;
  onRemove: () => void;
  onMove: (to: number) => void;
}) {
  const t = useTranslations("jobs.questions");
  const tc = useTranslations("jobs.choices");
  const errorText = useErrorText();
  const { register, control, setValue, formState } = form;
  const all = useWatch({ control, name: "questions" }) ?? [];
  const q = all[index];
  const {
    fields: options,
    append,
    remove,
  } = useFieldArray({ control, name: `questions.${index}.options` });
  if (!q) return null;
  const errors = formState.errors.questions?.[index];
  const earlier = all.slice(0, index);
  const parent = earlier.find((e) => e.key === q.show_if_question);
  const modes = MODES_BY_TYPE[q.type] ?? ["none"];
  const values = optionValuesFor(q);
  const prefix = `field-q-${index}`;
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-4">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-medium">
            {t("question")} {index + 1}
            {q.prompt ? `: ${q.prompt.slice(0, 60)}` : ""}
          </h3>
          <div className="flex gap-1">
            <Button
              type="button"
              size="icon"
              variant="ghost"
              aria-label={t("moveUp", { n: index + 1 })}
              disabled={index === 0}
              onClick={() => onMove(index - 1)}
            >
              <ArrowUp aria-hidden="true" />
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              aria-label={t("moveDown", { n: index + 1 })}
              disabled={index === total - 1}
              onClick={() => onMove(index + 1)}
            >
              <ArrowDown aria-hidden="true" />
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              aria-label={t("remove", { n: index + 1 })}
              onClick={onRemove}
            >
              <Trash2 aria-hidden="true" />
            </Button>
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${prefix}-prompt`}>{t("prompt")}</Label>
          <Input
            id={`${prefix}-prompt`}
            className="h-10"
            aria-invalid={errors?.prompt ? true : undefined}
            {...register(`questions.${index}.prompt`)}
          />
          {errors?.prompt ? (
            <p className="text-destructive text-sm" role="alert">
              {errorText(errors.prompt.message)}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${prefix}-help`}>{t("helpText")}</Label>
          <Input
            id={`${prefix}-help`}
            className="h-10"
            {...register(`questions.${index}.help_text`)}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <SelectField
            label={t("type")}
            options={QUESTION_TYPES.map((v) => ({ value: v, label: tc(`question.${v}`) }))}
            {...register(`questions.${index}.type`, {
              onChange: () => {
                setValue(`questions.${index}.scoring_mode`, "none");
                setValue(`questions.${index}.is_knockout`, false);
              },
            })}
          />
          <SelectField
            label={t("scoring")}
            description={q.type === "salary_expectation" ? t("salaryNeverScored") : undefined}
            options={modes
              .filter((m) => m !== "range" || q.scoring_raw.mode === "range")
              .map((m) => ({ value: m, label: tc(`scoring.${m}`) }))}
            {...register(`questions.${index}.scoring_mode`)}
          />
          <label className="flex min-h-6 items-center gap-2 self-end pb-2 text-sm">
            <input
              type="checkbox"
              className="size-4"
              {...register(`questions.${index}.required`)}
            />
            {t("required")}
          </label>
        </div>

        {CHOICE_TYPES.includes(q.type) ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium">{t("options")}</legend>
            {options.map((o, oi) => (
              <div key={o.id} className="flex items-end gap-2">
                <div className="flex flex-1 flex-col gap-1">
                  <Label htmlFor={`${prefix}-opt-${oi}`} className="sr-only">
                    {t("optionLabel", { n: oi + 1 })}
                  </Label>
                  <Input
                    id={`${prefix}-opt-${oi}`}
                    className="h-10"
                    placeholder={t("optionLabel", { n: oi + 1 })}
                    {...register(`questions.${index}.options.${oi}.label`, {
                      onChange: (e: { target: { value: string } }) => {
                        const taken = new Set(
                          all[index]!.options.filter((_, j) => j !== oi).map((x) => x.value),
                        );
                        setValue(
                          `questions.${index}.options.${oi}.value`,
                          slugKey(e.target.value, taken),
                        );
                      },
                    })}
                  />
                </div>
                {q.scoring_mode === "options" ? (
                  <div className="flex w-24 flex-col gap-1">
                    <Label htmlFor={`${prefix}-pts-${oi}`} className="text-xs">
                      {t("points")}
                    </Label>
                    <Input
                      id={`${prefix}-pts-${oi}`}
                      inputMode="decimal"
                      className="h-10"
                      {...register(`questions.${index}.options.${oi}.points`)}
                    />
                  </div>
                ) : null}
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label={t("removeOption", { n: oi + 1 })}
                  onClick={() => remove(oi)}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </div>
            ))}
            <div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => append({ label: "", value: "", points: "" })}
              >
                <Plus aria-hidden="true" />
                {t("addOption")}
              </Button>
            </div>
            {errors?.options?.message ? (
              <p className="text-destructive text-sm" role="alert">
                {errorText(errors.options.message)}
              </p>
            ) : null}
          </fieldset>
        ) : null}

        {q.scoring_mode === "exact" ? (
          values.length > 0 ? (
            <SelectField
              label={t("expected")}
              error={errors?.expected}
              options={[
                { value: "", label: t("choose") },
                ...values.map((v) => ({ value: v, label: v })),
              ]}
              {...register(`questions.${index}.expected`)}
            />
          ) : (
            <div className="flex flex-col gap-1.5 sm:w-48">
              <Label htmlFor={`${prefix}-expected`}>{t("expected")}</Label>
              <Input
                id={`${prefix}-expected`}
                className="h-10"
                {...register(`questions.${index}.expected`)}
              />
            </div>
          )
        ) : null}
        {q.scoring_mode === "rubric_text" ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${prefix}-keywords`}>{t("keywords")}</Label>
            <Input
              id={`${prefix}-keywords`}
              className="h-10"
              aria-describedby={`${prefix}-keywords-desc`}
              {...register(`questions.${index}.keywords`)}
            />
            <p id={`${prefix}-keywords-desc`} className="text-muted-foreground text-xs">
              {t("keywordsHelp")}
            </p>
            {errors?.keywords ? (
              <p className="text-destructive text-sm" role="alert">
                {errorText(errors.keywords.message)}
              </p>
            ) : null}
          </div>
        ) : null}

        {(["yes_no", "single_choice", "number"] as QuestionType[]).includes(q.type) ? (
          <div className="flex flex-col gap-2 rounded-md border p-3">
            <label className="flex min-h-6 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4"
                {...register(`questions.${index}.is_knockout`)}
              />
              {t("knockout")}
            </label>
            <p className="text-muted-foreground text-xs">{t("knockoutHelp")}</p>
            {q.is_knockout ? (
              values.length > 0 ? (
                <SelectField
                  label={t("knockoutExpected")}
                  error={errors?.knockout_expected}
                  options={[
                    { value: "", label: t("choose") },
                    ...values.map((v) => ({ value: v, label: v })),
                  ]}
                  {...register(`questions.${index}.knockout_expected`)}
                />
              ) : (
                <div className="flex flex-col gap-1.5 sm:w-48">
                  <Label htmlFor={`${prefix}-ko`}>{t("knockoutExpected")}</Label>
                  <Input
                    id={`${prefix}-ko`}
                    className="h-10"
                    {...register(`questions.${index}.knockout_expected`)}
                  />
                </div>
              )
            ) : null}
          </div>
        ) : null}

        {index > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <SelectField
              label={t("showIf")}
              description={t("showIfHelp")}
              options={[
                { value: "", label: t("always") },
                ...earlier
                  .filter((e) => optionValuesFor(e).length > 0)
                  .map((e) => ({ value: e.key, label: e.prompt.slice(0, 60) || e.key })),
              ]}
              {...register(`questions.${index}.show_if_question`, {
                onChange: () => setValue(`questions.${index}.show_if_value`, ""),
              })}
            />
            {parent ? (
              <SelectField
                label={t("showIfValue")}
                options={[
                  { value: "", label: t("choose") },
                  ...optionValuesFor(parent).map((v) => ({ value: v, label: v })),
                ]}
                {...register(`questions.${index}.show_if_value`)}
              />
            ) : null}
          </div>
        ) : null}
        <ProtectedTopicNotice q={q} index={index} />
      </CardContent>
    </Card>
  );
}

export function QuestionsStep() {
  const t = useTranslations("jobs.questions");
  const { job, api, save } = useWizard();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { questions: questionsFromJob(job) },
    mode: "onBlur",
  });
  const { control, handleSubmit, formState, reset } = form;
  const { fields, append, remove, move } = useFieldArray({ control, name: "questions" });
  const values = useWatch({ control });

  const persist = async (data: FormValues): Promise<boolean> => {
    setFormError(null);
    const result = await save((lock) =>
      api.setQuestionnaire(job.id, questionsToInput(data.questions), lock),
    );
    if (result instanceof ApiError) {
      if (result.code !== "conflict.stale_version") setFormError(result.message);
      return false;
    }
    // Server recomputes protected-topic flags; show them immediately.
    reset({ questions: questionsFromJob(result) });
    return true;
  };
  const submit = () =>
    new Promise<boolean>((resolve) => {
      void handleSubmit(
        async (d) => resolve(await persist(d)),
        () => resolve(false),
      )();
    });
  useAutosave(values, formState.isDirty && formSchema.safeParse(values).success, () => {
    void handleSubmit((d) => void persist(d))();
  });

  const taken = () => new Set((values.questions ?? []).map((q) => q?.key ?? ""));
  const addFromBank = (key: string) => {
    const item = BANK.find((b) => b.key === key);
    if (!item) return;
    append({
      ...emptyQuestion(taken()),
      key: slugKey(key.replaceAll("_", "-"), taken()),
      type: item.type,
      prompt: t(`bank.${key}`),
    });
  };

  return (
    <form
      method="post"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="flex flex-col gap-4"
    >
      <div>
        <h2 className="text-lg font-semibold">{t("title")}</h2>
        <p className="text-muted-foreground text-sm">{t("intro")}</p>
      </div>
      <Alert role="note">
        <AlertDescription>{t("fairness")}</AlertDescription>
      </Alert>
      <ErrorSummary
        errors={{}}
        formError={formError}
        labels={{}}
        submitCount={formState.submitCount}
      />
      {fields.length === 0 ? (
        <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
          {t("empty")}
        </p>
      ) : null}
      {fields.map((f, i) => (
        <QuestionCard
          key={f.id}
          index={i}
          total={fields.length}
          form={form}
          onRemove={() => remove(i)}
          onMove={(to) => move(i, to)}
        />
      ))}
      <div className="flex flex-wrap items-end gap-3">
        <Button
          type="button"
          variant="outline"
          className="min-h-10"
          disabled={fields.length >= 60}
          onClick={() => append(emptyQuestion(taken()))}
        >
          <Plus aria-hidden="true" />
          {t("add")}
        </Button>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="question-bank">{t("bankLabel")}</Label>
          <select
            id="question-bank"
            className="border-input bg-background h-10 rounded-md border px-2 text-sm"
            value=""
            onChange={(e) => addFromBank(e.target.value)}
          >
            <option value="">{t("bankChoose")}</option>
            {BANK.map((b) => (
              <option key={b.key} value={b.key}>
                {t(`bank.${b.key}`)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <StepFooter step="questions" onSave={submit} />
    </form>
  );
}
