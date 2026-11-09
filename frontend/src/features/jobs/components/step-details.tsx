"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "next-intl";
import { useContext, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";

import { ErrorSummary, SelectField, TextField, useErrorText } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { applyServerErrors } from "@/features/auth/form-errors";
import { useDepartments, useLocations } from "@/features/organisations/hooks";
import { ApiError } from "@/lib/api-client";
import { COMMON_TIMEZONES, utcIsoToZonedLocal, zonedLocalToUtcIso } from "@/lib/timezone";

import type { JobDetail, JobPatch } from "../api";
import { jobKeys, useJobsContext } from "../hooks";
import {
  DOCUMENT_TYPES,
  EMPLOYMENT_TYPES,
  SENIORITIES,
  WORKPLACE_TYPES,
  detailsFromJob,
  detailsSchema,
  type DetailsValues,
} from "../schemas";
import { RichTextEditor } from "./rich-text-editor";
import { useAutosave } from "./use-autosave";
import { StepFooter, WizardContext } from "./wizard-context";

const LIVE = new Set(["published", "paused", "scheduled"]);

/** Map form values to the API payload (UTC deadline, nulls for blanks). */
export function toPayload(values: DetailsValues, job?: JobDetail): JobPatch {
  const payload: JobPatch = {
    title: values.title,
    reference_code: values.reference_code,
    department_id: values.department_id || null,
    location_ids: values.location_ids,
    workplace_type: values.workplace_type,
    employment_type: values.employment_type,
    seniority: values.seniority,
    openings: values.openings,
    timezone: values.timezone,
    salary_min: values.salary_min || null,
    salary_max: values.salary_max || null,
    salary_currency: values.salary_currency,
    salary_period: values.salary_period,
    salary_disclosed: values.salary_disclosed,
    visibility: values.visibility,
    summary: values.summary,
    responsibilities_html: values.responsibilities_html,
    requirements_html: values.requirements_html,
    benefits_html: values.benefits_html,
    required_documents: values.required_documents,
  };
  // Live vacancies change their deadline through "Extend deadline" (audited), not the editor.
  if (!job || !LIVE.has(job.status)) {
    payload.closes_at = values.closes_at_local
      ? zonedLocalToUtcIso(values.closes_at_local, values.timezone)
      : null;
  }
  return payload;
}

const FIELD_MAP = {
  title: "title",
  reference_code: "reference_code",
  openings: "openings",
  closes_at: "closes_at_local",
  timezone: "timezone",
  salary_min: "salary_min",
  salary_max: "salary_max",
  department_id: "department_id",
  location_ids: "location_ids",
  required_documents: "required_documents",
  summary: "summary",
} as const;

export function DetailsStep({ onCreated }: { onCreated?: (job: JobDetail) => void }) {
  const t = useTranslations("jobs.details");
  const tc = useTranslations("jobs.choices");
  const format = useFormatter();
  const wizard = useContext(WizardContext);
  const job = wizard?.job;
  const { orgId, api } = useJobsContext();
  const client = useQueryClient();
  const departments = useDepartments(orgId ?? undefined);
  const locations = useLocations(orgId ?? undefined);
  const errorText = useErrorText();
  const [formError, setFormError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const form = useForm<DetailsValues>({
    resolver: zodResolver(detailsSchema),
    defaultValues: detailsFromJob(job, (iso, tz) => utcIsoToZonedLocal(iso, tz)),
    mode: "onBlur",
  });
  const { register, handleSubmit, formState, control, setError, reset } = form;
  const values = useWatch({ control });
  const tz = values.timezone ?? "Africa/Harare";
  const closesIso = values.closes_at_local ? zonedLocalToUtcIso(values.closes_at_local, tz) : null;

  const persist = async (data: DetailsValues): Promise<boolean> => {
    setFormError(null);
    if (!job) {
      setCreating(true);
      try {
        const created = await api!.create({ ...toPayload(data), title: data.title });
        client.setQueryData(jobKeys.detail(orgId!, created.id), created);
        onCreated?.(created);
        return true;
      } catch (err) {
        setFormError(applyServerErrors(err, setError, FIELD_MAP));
        return false;
      } finally {
        setCreating(false);
      }
    }
    const result = await wizard!.save((lock) =>
      api!.update(job.id, { ...toPayload(data, job), lock_version: lock }),
    );
    if (result instanceof ApiError) {
      if (result.code !== "conflict.stale_version")
        setFormError(applyServerErrors(result, setError, FIELD_MAP));
      return false;
    }
    reset(data, { keepValues: true });
    return true;
  };

  const submit = () =>
    new Promise<boolean>((resolve) => {
      void handleSubmit(
        async (data) => resolve(await persist(data)),
        () => resolve(false),
      )();
    });

  // EC-JOB-07 friendly autosave: only existing drafts, only when dirty and valid.
  useAutosave(values, !!job && formState.isDirty && detailsSchema.safeParse(values).success, () => {
    void handleSubmit((data) => void persist(data))();
  });

  const labels: Record<string, string> = {
    title: t("title"),
    openings: t("openings"),
    closes_at_local: t("closesAt"),
    salary_max: t("salaryMax"),
    salary_min: t("salaryMin"),
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
      <ErrorSummary
        errors={formState.errors}
        formError={formError}
        labels={labels}
        submitCount={formState.submitCount}
      />
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("basics")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <TextField
            label={t("title")}
            required
            error={formState.errors.title}
            className="sm:col-span-2"
            {...register("title")}
          />
          <TextField
            label={t("reference")}
            error={formState.errors.reference_code}
            {...register("reference_code")}
          />
          <SelectField
            label={t("department")}
            options={[
              { value: "", label: t("noDepartment") },
              ...(departments.data?.results ?? []).map((d) => ({ value: d.id, label: d.name })),
            ]}
            {...register("department_id")}
          />
          <SelectField
            label={t("employmentType")}
            options={EMPLOYMENT_TYPES.map((v) => ({ value: v, label: tc(`employment.${v}`) }))}
            {...register("employment_type")}
          />
          <SelectField
            label={t("workplaceType")}
            options={WORKPLACE_TYPES.map((v) => ({ value: v, label: tc(`workplace.${v}`) }))}
            {...register("workplace_type")}
          />
          <SelectField
            label={t("seniority")}
            options={SENIORITIES.map((v) => ({
              value: v,
              label: v ? tc(`seniority.${v}`) : t("notSpecified"),
            }))}
            {...register("seniority")}
          />
          <TextField
            label={t("openings")}
            type="number"
            min={1}
            max={1000}
            required
            error={formState.errors.openings}
            {...register("openings", { valueAsNumber: true })}
          />
          <fieldset className="flex flex-col gap-1.5 sm:col-span-2">
            <legend className="text-sm font-medium">{t("locations")}</legend>
            {(locations.data?.results ?? []).length === 0 ? (
              <p className="text-muted-foreground text-sm">{t("noLocations")}</p>
            ) : (
              <div className="flex flex-wrap gap-3">
                {(locations.data?.results ?? []).map((loc) => (
                  <label key={loc.id} className="flex min-h-6 items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      value={loc.id}
                      className="size-4"
                      {...register("location_ids")}
                    />
                    {loc.name}
                    {loc.city ? <span className="text-muted-foreground">({loc.city})</span> : null}
                  </label>
                ))}
              </div>
            )}
          </fieldset>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("deadline")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <TextField
            label={t("closesAt")}
            type="datetime-local"
            required
            disabled={!!job && LIVE.has(job.status)}
            description={job && LIVE.has(job.status) ? t("useExtend") : t("closesAtHelp", { tz })}
            error={formState.errors.closes_at_local}
            {...register("closes_at_local")}
          />
          <SelectField
            label={t("timezone")}
            options={[...new Set([tz, ...COMMON_TIMEZONES])].map((z) => ({ value: z, label: z }))}
            {...register("timezone")}
          />
          {closesIso ? (
            <p className="text-muted-foreground text-sm sm:col-span-2" aria-live="polite">
              {t("closesPreview", {
                jobTime: format.dateTime(new Date(closesIso), {
                  dateStyle: "full",
                  timeStyle: "short",
                  timeZone: tz,
                }),
                viewerTime: format.dateTime(new Date(closesIso), {
                  dateStyle: "medium",
                  timeStyle: "short",
                }),
              })}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("pay")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-4">
          <TextField
            label={t("salaryMin")}
            inputMode="decimal"
            error={formState.errors.salary_min}
            {...register("salary_min")}
          />
          <TextField
            label={t("salaryMax")}
            inputMode="decimal"
            error={formState.errors.salary_max}
            {...register("salary_max")}
          />
          <SelectField
            label={t("currency")}
            options={[
              { value: "USD", label: "USD" },
              { value: "ZWG", label: "ZWG" },
            ]}
            {...register("salary_currency")}
          />
          <SelectField
            label={t("period")}
            options={(["hour", "day", "month", "year"] as const).map((v) => ({
              value: v,
              label: tc(`period.${v}`),
            }))}
            {...register("salary_period")}
          />
          <label className="flex min-h-6 items-center gap-2 text-sm sm:col-span-4">
            <input type="checkbox" className="size-4" {...register("salary_disclosed")} />
            {t("salaryDisclosed")}
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">{t("advert")}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="field-summary">{t("summary")}</Label>
            <textarea
              id="field-summary"
              rows={3}
              maxLength={2000}
              className="border-input bg-background rounded-md border px-3 py-2 text-sm"
              aria-describedby="field-summary-desc"
              {...register("summary")}
            />
            <p id="field-summary-desc" className="text-muted-foreground text-xs">
              {t("summaryHelp")}
            </p>
            {formState.errors.summary ? (
              <p className="text-destructive text-sm" role="alert">
                {errorText(formState.errors.summary.message)}
              </p>
            ) : null}
          </div>
          {(["responsibilities_html", "requirements_html", "benefits_html"] as const).map(
            (name) => (
              <Controller
                key={name}
                control={control}
                name={name}
                render={({ field }) => (
                  <RichTextEditor
                    name={name}
                    label={t(name)}
                    value={field.value}
                    onChange={field.onChange}
                  />
                )}
              />
            ),
          )}
          <fieldset className="flex flex-col gap-1.5">
            <legend className="text-sm font-medium">{t("requiredDocuments")}</legend>
            <div className="flex flex-wrap gap-3">
              {DOCUMENT_TYPES.map((d) => (
                <label key={d} className="flex min-h-6 items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    value={d}
                    className="size-4"
                    {...register("required_documents")}
                  />
                  {tc(`documents.${d}`)}
                </label>
              ))}
            </div>
          </fieldset>
          <SelectField
            label={t("visibility")}
            description={t("visibilityHelp")}
            options={(["public", "unlisted"] as const).map((v) => ({
              value: v,
              label: tc(`visibility.${v}`),
            }))}
            {...register("visibility")}
          />
        </CardContent>
      </Card>

      {job ? (
        <StepFooter step="details" onSave={submit} />
      ) : (
        <div className="flex justify-end">
          <Button type="submit" className="min-h-10" disabled={creating}>
            {creating ? t("creating") : t("createDraft")}
          </Button>
        </div>
      )}
    </form>
  );
}
