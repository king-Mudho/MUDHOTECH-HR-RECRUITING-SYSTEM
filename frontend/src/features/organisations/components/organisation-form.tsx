"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ErrorSummary, SelectField, TextField } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { applyServerErrors } from "@/features/auth/form-errors";

import { ORG_DEFAULTS, organisationSchema, type OrganisationValues } from "../schemas";

const FIELDS = [
  "name",
  "legal_name",
  "registration_number",
  "industry",
  "size_band",
  "country",
  "city",
  "website",
  "description",
] as const;

/** Shared organisation details form (employer sign-up + HR settings profile). */
export function OrganisationForm({
  initial,
  submitLabel,
  onSubmit,
  readOnly = false,
}: {
  initial?: Partial<OrganisationValues>;
  submitLabel: string;
  onSubmit: (values: OrganisationValues) => Promise<void>;
  readOnly?: boolean;
}) {
  const t = useTranslations("organisations.fields");
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const form = useForm<OrganisationValues>({
    resolver: zodResolver(organisationSchema),
    defaultValues: { ...ORG_DEFAULTS, ...initial },
  });
  const submit = form.handleSubmit(async (values) => {
    setFormError(null);
    setSaved(false);
    try {
      await onSubmit(values);
      setSaved(true);
    } catch (err) {
      const map = Object.fromEntries(FIELDS.map((f) => [f, f])) as Record<
        string,
        (typeof FIELDS)[number]
      >;
      setFormError(applyServerErrors(err, form.setError, map));
    }
  });
  const labels = Object.fromEntries(FIELDS.map((f) => [f, t(f)]));
  const e = form.formState.errors;
  return (
    <form method="post" onSubmit={submit} noValidate className="flex flex-col gap-4">
      <ErrorSummary
        errors={e}
        formError={formError}
        labels={labels}
        submitCount={form.formState.submitCount}
      />
      <fieldset
        disabled={readOnly || form.formState.isSubmitting}
        className="grid gap-4 sm:grid-cols-2"
      >
        <TextField
          className="sm:col-span-2"
          label={t("name")}
          required
          error={e.name}
          {...form.register("name")}
        />
        <TextField label={t("legal_name")} error={e.legal_name} {...form.register("legal_name")} />
        <TextField
          label={t("registration_number")}
          error={e.registration_number}
          {...form.register("registration_number")}
        />
        <TextField label={t("industry")} error={e.industry} {...form.register("industry")} />
        <SelectField
          label={t("size_band")}
          options={[
            { value: "", label: t("sizeUnknown") },
            ...["1-9", "10-49", "50-249", "250-999", "1000+"].map((v) => ({ value: v, label: v })),
          ]}
          error={e.size_band}
          {...form.register("size_band")}
        />
        <TextField label={t("city")} error={e.city} {...form.register("city")} />
        <TextField
          label={t("country")}
          description={t("countryHelp")}
          maxLength={2}
          error={e.country}
          {...form.register("country", { setValueAs: (v: string) => v.toUpperCase() })}
        />
        <TextField
          className="sm:col-span-2"
          label={t("website")}
          type="url"
          placeholder="https://"
          error={e.website}
          {...form.register("website")}
        />
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="field-description">{t("description")}</Label>
          <textarea
            id="field-description"
            rows={5}
            className="border-input bg-background rounded-md border p-2 text-sm"
            aria-describedby="field-description-desc"
            {...form.register("description")}
          />
          <p id="field-description-desc" className="text-muted-foreground text-xs">
            {t("descriptionHelp")}
          </p>
        </div>
      </fieldset>
      {saved ? (
        <p role="status" className="text-success text-sm">
          {t("saved")}
        </p>
      ) : null}
      {!readOnly ? (
        <Button
          type="submit"
          className="min-h-10 self-start"
          disabled={form.formState.isSubmitting}
        >
          {submitLabel}
        </Button>
      ) : null}
    </form>
  );
}
