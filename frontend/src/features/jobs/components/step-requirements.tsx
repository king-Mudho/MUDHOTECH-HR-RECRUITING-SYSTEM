"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Sparkles, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useId, useState } from "react";
import { useFieldArray, useForm, useWatch, type UseFormReturn } from "react-hook-form";

import { ErrorSummary, SelectField, useErrorText } from "@/components/forms/form-field";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";

import type { Suggestions } from "../api";
import {
  CRITERION_TYPES,
  RUBRIC_KEYS,
  criteriaFormSchema,
  criteriaFromJob,
  criteriaToInput,
  defaultCategory,
  emptyCriterion,
  type CriteriaFormValues,
  type CriterionValues,
} from "../schemas";
import { useAutosave } from "./use-autosave";
import { StepFooter, useWizard } from "./wizard-context";

function SkillAutocomplete({
  index,
  form,
}: {
  index: number;
  form: UseFormReturn<CriteriaFormValues>;
}) {
  const t = useTranslations("jobs.requirements");
  const { api } = useWizard();
  const listId = useId();
  const title = useWatch({ control: form.control, name: `criteria.${index}.title` });
  const skillId = useWatch({ control: form.control, name: `criteria.${index}.skill_id` });
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState(title);
  useEffect(() => {
    const id = setTimeout(() => setTerm(title), 250);
    return () => clearTimeout(id);
  }, [title]);
  const skills = useQuery({
    queryKey: ["taxonomy", "skills", term],
    queryFn: () => api.skills(term),
    enabled: open && term.trim().length >= 2,
    staleTime: 60_000,
  });
  const options = skills.data ?? [];
  const error = form.formState.errors.criteria?.[index]?.title;
  const errorText = useErrorText()(error?.message);
  const field = form.register(`criteria.${index}.title`, {
    onChange: () => {
      form.setValue(`criteria.${index}.skill_id`, null);
      setOpen(true);
    },
  });
  return (
    <div className="relative flex flex-col gap-1.5">
      <Label htmlFor={`field-criteria-${index}-title`}>{t("criterionTitle")}</Label>
      <Input
        id={`field-criteria-${index}-title`}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open && options.length > 0}
        aria-controls={listId}
        aria-invalid={errorText ? true : undefined}
        autoComplete="off"
        className="h-10"
        {...field}
        onBlur={(e) => {
          void field.onBlur(e);
          setTimeout(() => setOpen(false), 150);
        }}
      />
      {skillId ? (
        <Badge variant="secondary" className="w-fit">
          {t("linkedToTaxonomy")}
        </Badge>
      ) : null}
      {open && options.length > 0 ? (
        <ul
          id={listId}
          role="listbox"
          className="bg-popover absolute top-full z-10 mt-1 max-h-60 w-full overflow-auto rounded-md border shadow-md"
        >
          {options.map((s) => (
            <li
              key={s.id}
              role="option"
              aria-selected={s.id === skillId}
              tabIndex={-1}
              className="hover:bg-muted cursor-pointer px-3 py-2 text-sm"
              onMouseDown={(e) => {
                e.preventDefault();
                form.setValue(`criteria.${index}.title`, s.canonical_name, { shouldDirty: true });
                form.setValue(`criteria.${index}.skill_id`, s.id, { shouldDirty: true });
                setOpen(false);
              }}
            >
              {s.canonical_name}
              {s.is_custom ? (
                <span className="text-muted-foreground ml-2 text-xs">{t("custom")}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {errorText ? (
        <p className="text-destructive text-sm" role="alert">
          {errorText}
        </p>
      ) : null}
    </div>
  );
}

function CriterionCard({
  index,
  total,
  form,
  onRemove,
  onMove,
}: {
  index: number;
  total: number;
  form: UseFormReturn<CriteriaFormValues>;
  onRemove: () => void;
  onMove: (to: number) => void;
}) {
  const t = useTranslations("jobs.requirements");
  const tc = useTranslations("jobs.choices");
  const errorText = useErrorText();
  const { register, control, setValue, formState } = form;
  const c = useWatch({ control, name: `criteria.${index}` });
  const errors = formState.errors.criteria?.[index];
  const groupLabel = `${t("criterion")} ${index + 1}${c?.title ? `: ${c.title}` : ""}`;
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-4">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-medium">{groupLabel}</h3>
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
        <div className="grid gap-3 sm:grid-cols-3">
          <SelectField
            label={t("type")}
            options={CRITERION_TYPES.map((v) => ({ value: v, label: tc(`criterion.${v}`) }))}
            {...register(`criteria.${index}.type`, {
              onChange: (e: { target: { value: (typeof CRITERION_TYPES)[number] } }) =>
                setValue(`criteria.${index}.rubric_category`, defaultCategory(e.target.value)),
            })}
          />
          <fieldset className="flex flex-col gap-1.5">
            <legend className="text-sm font-medium">{t("importance")}</legend>
            <div className="flex gap-4">
              {(["essential", "preferred"] as const).map((v) => (
                <label key={v} className="flex min-h-6 items-center gap-2 text-sm">
                  <input
                    type="radio"
                    value={v}
                    className="size-4"
                    {...register(`criteria.${index}.importance`)}
                  />
                  {tc(`importance.${v}`)}
                </label>
              ))}
            </div>
          </fieldset>
          <SelectField
            label={t("rubricCategory")}
            options={RUBRIC_KEYS.map((v) => ({ value: v, label: tc(`rubric.${v}`) }))}
            {...register(`criteria.${index}.rubric_category`)}
          />
        </div>
        {c?.type === "skill" ? (
          <SkillAutocomplete index={index} form={form} />
        ) : (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`field-criteria-${index}-title`}>{t("criterionTitle")}</Label>
            <Input
              id={`field-criteria-${index}-title`}
              className="h-10"
              aria-invalid={errors?.title ? true : undefined}
              {...register(`criteria.${index}.title`)}
            />
            {errors?.title ? (
              <p className="text-destructive text-sm" role="alert">
                {errorText(errors.title.message)}
              </p>
            ) : null}
          </div>
        )}
        {c?.type === "experience" ? (
          <div className="flex flex-col gap-1.5 sm:w-48">
            <Label htmlFor={`field-criteria-${index}-months`}>{t("minMonths")}</Label>
            <Input
              id={`field-criteria-${index}-months`}
              type="number"
              min={0}
              max={600}
              className="h-10"
              {...register(`criteria.${index}.min_months`, {
                setValueAs: (v: string) => (v === "" || v === null ? null : Number(v)),
              })}
            />
          </div>
        ) : null}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`field-criteria-${index}-justification`}>
            {t("justification")}
            {c?.importance === "essential" ? (
              <span className="text-muted-foreground font-normal">
                {" "}
                {t("requiredForEssential")}
              </span>
            ) : null}
          </Label>
          <textarea
            id={`field-criteria-${index}-justification`}
            rows={2}
            className="border-input bg-background rounded-md border px-3 py-2 text-sm"
            aria-invalid={errors?.justification ? true : undefined}
            aria-describedby={`field-criteria-${index}-justification-desc`}
            {...register(`criteria.${index}.justification`)}
          />
          <p
            id={`field-criteria-${index}-justification-desc`}
            className="text-muted-foreground text-xs"
          >
            {t("justificationHelp")}
          </p>
          {errors?.justification ? (
            <p className="text-destructive text-sm" role="alert">
              {errorText(errors.justification.message)}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`field-criteria-${index}-equivalents`}>{t("equivalents")}</Label>
          <Input
            id={`field-criteria-${index}-equivalents`}
            className="h-10"
            aria-describedby={`field-criteria-${index}-equivalents-desc`}
            defaultValue={(c?.equivalents ?? []).join(", ")}
            onChange={(e) =>
              setValue(
                `criteria.${index}.equivalents`,
                e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
                { shouldDirty: true },
              )
            }
          />
          <p
            id={`field-criteria-${index}-equivalents-desc`}
            className="text-muted-foreground text-xs"
          >
            {t("equivalentsHelp")}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function SuggestionsPanel({
  existing,
  onAccept,
}: {
  existing: CriterionValues[];
  onAccept: (c: CriterionValues) => void;
}) {
  const t = useTranslations("jobs.requirements.ai");
  const tCommon = useTranslations("common");
  const { api, job } = useWizard();
  const [data, setData] = useState<Suggestions | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "disabled" | "error">("idle");
  const load = async () => {
    setState("loading");
    try {
      setData(await api.suggestions(job.id));
      setState("idle");
    } catch (err) {
      setState(err instanceof ApiError && err.code === "feature_disabled" ? "disabled" : "error");
    }
  };
  const taken = new Set(existing.map((c) => c.title.toLowerCase()));
  const items = (data?.criteria ?? []).filter((c) => !taken.has(String(c.title).toLowerCase()));
  return (
    <section aria-labelledby="ai-suggestions" className="rounded-lg border border-dashed p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="ai-suggestions" className="flex items-center gap-2 font-medium">
          <Sparkles aria-hidden="true" className="size-4" />
          {t("title")}
        </h3>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void load()}
          disabled={state === "loading"}
        >
          {state === "loading" ? t("loading") : t("get")}
        </Button>
      </div>
      <p className="text-muted-foreground mt-1 text-xs">{tCommon("aiLabel")}</p>
      <div aria-live="polite">
        {state === "disabled" ? <p className="mt-2 text-sm">{t("disabled")}</p> : null}
        {state === "error" ? <p className="text-destructive mt-2 text-sm">{t("error")}</p> : null}
        {data && items.length === 0 ? <p className="mt-2 text-sm">{t("none")}</p> : null}
      </div>
      {items.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-2">
          {items.map((s) => (
            <li
              key={String(s.skill_id ?? s.title)}
              className="flex items-center justify-between gap-2 text-sm"
            >
              <span>
                {String(s.title)} <span className="text-muted-foreground">— {t("reason")}</span>
              </span>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() =>
                  onAccept({
                    ...emptyCriterion(),
                    type: "skill",
                    importance: "preferred",
                    title: String(s.title),
                    skill_id: s.skill_id ? String(s.skill_id) : null,
                    rubric_category: "technical",
                  })
                }
              >
                {t("accept", { title: String(s.title) })}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function RequirementsStep() {
  const t = useTranslations("jobs.requirements");
  const { job, api, save } = useWizard();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<CriteriaFormValues>({
    resolver: zodResolver(criteriaFormSchema),
    defaultValues: { criteria: criteriaFromJob(job) },
    mode: "onBlur",
  });
  const { control, handleSubmit, formState, reset } = form;
  const { fields, append, remove, move } = useFieldArray({ control, name: "criteria" });
  const values = useWatch({ control });
  const criteria = (values.criteria ?? []) as CriterionValues[];
  const essential = criteria.filter((c) => c.importance === "essential").length;

  const persist = async (data: CriteriaFormValues): Promise<boolean> => {
    setFormError(null);
    const result = await save((lock) =>
      api.setCriteria(job.id, criteriaToInput(data.criteria), lock),
    );
    if (result instanceof ApiError) {
      if (result.code !== "conflict.stale_version") setFormError(result.message);
      return false;
    }
    reset(data, { keepValues: true });
    return true;
  };
  const submit = () =>
    new Promise<boolean>((resolve) => {
      void handleSubmit(
        async (d) => resolve(await persist(d)),
        () => resolve(false),
      )();
    });
  useAutosave(values, formState.isDirty && criteriaFormSchema.safeParse(values).success, () => {
    void handleSubmit((d) => void persist(d))();
  });

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
      <ErrorSummary
        errors={{}}
        formError={formError}
        labels={{}}
        submitCount={formState.submitCount}
      />
      {criteria.length > 0 && essential === 0 ? (
        <Alert role="status">
          <AlertDescription>{t("needEssential")}</AlertDescription>
        </Alert>
      ) : null}
      {criteria.length > 0 && essential === criteria.length ? (
        <Alert role="status">
          <AlertTitle>{t("allEssentialTitle")}</AlertTitle>
          <AlertDescription>{t("allEssential")}</AlertDescription>
        </Alert>
      ) : null}
      {fields.length === 0 ? (
        <p className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
          {t("empty")}
        </p>
      ) : null}
      {fields.map((f, i) => (
        <CriterionCard
          key={f.id}
          index={i}
          total={fields.length}
          form={form}
          onRemove={() => remove(i)}
          onMove={(to) => move(i, to)}
        />
      ))}
      <div>
        <Button
          type="button"
          variant="outline"
          className="min-h-10"
          onClick={() => append(emptyCriterion())}
          disabled={fields.length >= 40}
        >
          <Plus aria-hidden="true" />
          {t("add")}
        </Button>
      </div>
      <SuggestionsPanel existing={criteria} onAccept={(c) => append(c)} />
      <StepFooter step="requirements" onSave={submit} />
    </form>
  );
}
