"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ErrorSummary, SelectField, TextField } from "@/components/forms/form-field";
import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { applyServerErrors } from "@/features/auth/form-errors";
import { ApiError } from "@/lib/api-client";

import { candidateApi, type Profile, type SectionName } from "../api";
import { candidateKeys, useProfile, useSection } from "../hooks";

// ----------------------------------------------------------------------------- completeness
export function CompletenessMeter({ profile }: { profile: Profile }) {
  const t = useTranslations("candidate.profile");
  const value = profile.profile_completeness;
  return (
    <section aria-labelledby="completeness" className="rounded-lg border p-4">
      <h2 id="completeness" className="font-semibold">
        {t("completeness", { value })}
      </h2>
      <div
        role="progressbar"
        aria-labelledby="completeness"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        className="bg-muted mt-2 h-2 overflow-hidden rounded-full"
      >
        <div className="bg-primary h-full" style={{ width: `${value}%` }} />
      </div>
      {profile.missing.length > 0 ? (
        <>
          <p className="text-muted-foreground mt-3 text-sm">{t("missingIntro")}</p>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {profile.missing.map((m) => (
              <li key={m}>{t(`missing.${m}`)}</li>
            ))}
          </ul>
        </>
      ) : null}
      <p className="text-muted-foreground mt-3 text-xs">{t("completenessNote")}</p>
    </section>
  );
}

// ------------------------------------------------------------------------------- details
const detailsSchema = z.object({
  preferred_name: z.string().max(100),
  headline: z.string().max(160),
  summary: z.string().max(5000),
  city: z.string().max(100),
  phone_e164: z.string().max(30),
  linkedin: z.string().max(300),
  github: z.string().max(300),
  portfolio: z.string().max(300),
  availability: z.enum(["", "immediate", "notice", "not_looking"]),
  notice_period_days: z.string().regex(/^\d{0,3}$/, "outOfRange"),
  open_to_relocation: z.boolean(),
});
type DetailsValues = z.infer<typeof detailsSchema>;

function defaults(p: Profile): DetailsValues {
  const links = (p.links ?? {}) as Record<string, string>;
  return {
    preferred_name: p.preferred_name ?? "",
    headline: p.headline ?? "",
    summary: p.summary ?? "",
    city: p.city ?? "",
    phone_e164: p.phone_e164 ?? "",
    linkedin: links.linkedin ?? "",
    github: links.github ?? "",
    portfolio: links.portfolio ?? "",
    availability: (p.availability ?? "") as DetailsValues["availability"],
    notice_period_days: p.notice_period_days == null ? "" : String(p.notice_period_days),
    open_to_relocation: !!p.open_to_relocation,
  };
}

function DetailsForm({ profile }: { profile: Profile }) {
  const t = useTranslations("candidate.profile");
  const client = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const form = useForm<DetailsValues>({
    resolver: zodResolver(detailsSchema),
    defaultValues: defaults(profile),
  });
  const { register, handleSubmit, formState, setError, reset } = form;
  const save = useMutation({
    mutationFn: (v: DetailsValues) =>
      candidateApi.updateProfile({
        lock_version: profile.lock_version,
        preferred_name: v.preferred_name,
        headline: v.headline,
        summary: v.summary,
        city: v.city,
        phone_e164: v.phone_e164,
        links: { linkedin: v.linkedin, github: v.github, portfolio: v.portfolio },
        availability: v.availability,
        notice_period_days: v.notice_period_days === "" ? null : Number(v.notice_period_days),
        open_to_relocation: v.open_to_relocation,
      }),
    onSuccess: (data) => {
      client.setQueryData(candidateKeys.profile, data);
      reset(defaults(data));
      setSaved(true);
    },
    onError: (err) => {
      setSaved(false);
      if (err instanceof ApiError && err.code === "conflict.stale_version") {
        setFormError(t("conflict"));
        void client.invalidateQueries({ queryKey: candidateKeys.profile });
        return;
      }
      setFormError(
        applyServerErrors(err, setError, {
          phone_e164: "phone_e164",
          headline: "headline",
          summary: "summary",
        }),
      );
    },
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t("details")}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form
          method="post"
          noValidate
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={handleSubmit((v) => {
            setFormError(null);
            save.mutate(v);
          })}
        >
          <div className="sm:col-span-2">
            <ErrorSummary
              errors={formState.errors}
              formError={formError}
              labels={{}}
              submitCount={formState.submitCount}
            />
          </div>
          <TextField
            label={t("headline")}
            description={t("headlineHelp")}
            error={formState.errors.headline}
            className="sm:col-span-2"
            {...register("headline")}
          />
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="field-summary">{t("summary")}</Label>
            <textarea
              id="field-summary"
              rows={4}
              className="border-input bg-background rounded-md border px-3 py-2 text-sm"
              {...register("summary")}
            />
          </div>
          <TextField label={t("preferredName")} {...register("preferred_name")} />
          <TextField label={t("city")} autoComplete="address-level2" {...register("city")} />
          <TextField
            label={t("phone")}
            type="tel"
            autoComplete="tel"
            description={t("phoneHelp")}
            error={formState.errors.phone_e164}
            {...register("phone_e164")}
          />
          <SelectField
            label={t("availability")}
            options={[
              { value: "", label: t("notSaying") },
              { value: "immediate", label: t("availabilityOptions.immediate") },
              { value: "notice", label: t("availabilityOptions.notice") },
              { value: "not_looking", label: t("availabilityOptions.not_looking") },
            ]}
            {...register("availability")}
          />
          <TextField
            label={t("noticeDays")}
            inputMode="numeric"
            error={formState.errors.notice_period_days}
            {...register("notice_period_days")}
          />
          <label className="flex min-h-6 items-center gap-2 self-end pb-2 text-sm">
            <input type="checkbox" className="size-4" {...register("open_to_relocation")} />
            {t("relocation")}
          </label>
          <TextField label="LinkedIn" type="url" placeholder="https://" {...register("linkedin")} />
          <TextField label="GitHub" type="url" placeholder="https://" {...register("github")} />
          <TextField
            label={t("portfolio")}
            type="url"
            placeholder="https://"
            className="sm:col-span-2"
            {...register("portfolio")}
          />
          <div className="flex items-center gap-3 sm:col-span-2">
            <Button type="submit" className="min-h-10" disabled={save.isPending}>
              {t("save")}
            </Button>
            <p role="status" aria-live="polite" className="text-success text-sm">
              {saved && !formState.isDirty ? t("saved") : ""}
            </p>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------------------ sections
type FieldSpec = {
  name: string;
  type?: "text" | "date" | "number" | "select" | "checkbox" | "textarea";
  options?: string[];
  required?: boolean;
};

const SECTIONS: Record<
  SectionName,
  { fields: FieldSpec[]; title: (row: Record<string, unknown>) => string }
> = {
  experiences: {
    fields: [
      { name: "title", required: true },
      { name: "employer", required: true },
      { name: "location" },
      { name: "start_date", type: "date", required: true },
      { name: "end_date", type: "date" },
      { name: "is_current", type: "checkbox" },
      { name: "description", type: "textarea" },
    ],
    title: (r) => `${r.title} · ${r.employer}`,
  },
  educations: {
    fields: [
      { name: "qualification_text", required: true },
      { name: "institution", required: true },
      { name: "field" },
      { name: "start_date", type: "date" },
      { name: "end_date", type: "date" },
      { name: "grade" },
    ],
    title: (r) => `${r.qualification_text} · ${r.institution}`,
  },
  certifications: {
    fields: [
      { name: "name", required: true },
      { name: "issued_at", type: "date" },
      { name: "expires_at", type: "date" },
      { name: "credential_id" },
    ],
    title: (r) => String(r.name),
  },
  skills: {
    fields: [
      { name: "raw_name", required: true },
      {
        name: "proficiency",
        type: "select",
        options: ["", "beginner", "intermediate", "advanced", "expert"],
      },
      { name: "years", type: "number" },
    ],
    title: (r) => String(r.raw_name),
  },
  languages: {
    fields: [
      { name: "language", required: true },
      {
        name: "proficiency",
        type: "select",
        options: ["basic", "conversational", "fluent", "native"],
        required: true,
      },
    ],
    title: (r) => `${r.language} (${r.proficiency})`,
  },
};

function SectionItemForm({
  section,
  initial,
  onDone,
}: {
  section: SectionName;
  initial?: Record<string, unknown>;
  onDone: () => void;
}) {
  const t = useTranslations("candidate.profile");
  const client = useQueryClient();
  const spec = SECTIONS[section];
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(
      spec.fields.map((f) => [f.name, initial?.[f.name] ?? (f.type === "checkbox" ? false : "")]),
    ),
  );
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {};
      for (const f of spec.fields) {
        const v = values[f.name];
        body[f.name] = v === "" ? (f.type === "date" || f.type === "number" ? null : "") : v;
      }
      return initial?.id
        ? candidateApi.update(section, String(initial.id), body)
        : candidateApi.create(section, body);
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: candidateKeys.profile });
      onDone();
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors());
        setFormError(
          err.code === "conflict.duplicate"
            ? err.message
            : Object.keys(err.fieldErrors()).length
              ? null
              : err.message,
        );
      } else setFormError(t("failed"));
    },
  });
  return (
    <form
      method="post"
      noValidate
      className="grid gap-3 rounded-md border p-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
    >
      {formError ? (
        <p role="alert" className="text-destructive text-sm sm:col-span-2">
          {formError}
        </p>
      ) : null}
      {spec.fields.map((f) => {
        const id = `${section}-${f.name}-${String(initial?.id ?? "new")}`;
        const label = t(`fields.${f.name}`);
        const err = errors[f.name]?.join(" ");
        const common = {
          id,
          "aria-invalid": err ? true : undefined,
          "aria-describedby": err ? `${id}-err` : undefined,
        };
        if (f.type === "checkbox")
          return (
            <label key={f.name} className="flex min-h-6 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4"
                checked={!!values[f.name]}
                onChange={(e) => setValues({ ...values, [f.name]: e.target.checked })}
              />
              {label}
            </label>
          );
        return (
          <div
            key={f.name}
            className={
              f.type === "textarea"
                ? "flex flex-col gap-1.5 sm:col-span-2"
                : "flex flex-col gap-1.5"
            }
          >
            <Label htmlFor={id}>
              {label}
              {f.required ? (
                <span className="text-muted-foreground font-normal"> {t("required")}</span>
              ) : null}
            </Label>
            {f.type === "select" ? (
              <select
                {...common}
                className="border-input bg-background h-10 rounded-md border px-2 text-sm"
                value={String(values[f.name] ?? "")}
                onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
              >
                {f.options!.map((o) => (
                  <option key={o} value={o}>
                    {o ? t(`levels.${o}`) : t("notSaying")}
                  </option>
                ))}
              </select>
            ) : f.type === "textarea" ? (
              <textarea
                {...common}
                rows={3}
                className="border-input bg-background rounded-md border px-3 py-2 text-sm"
                value={String(values[f.name] ?? "")}
                onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
              />
            ) : (
              <input
                {...common}
                type={f.type ?? "text"}
                className="border-input bg-background h-10 rounded-md border px-3 text-sm"
                value={String(values[f.name] ?? "")}
                onChange={(e) =>
                  setValues({
                    ...values,
                    [f.name]:
                      f.type === "number" && e.target.value !== ""
                        ? Number(e.target.value)
                        : e.target.value,
                  })
                }
              />
            )}
            {err ? (
              <p id={`${id}-err`} className="text-destructive text-sm" role="alert">
                {err}
              </p>
            ) : null}
          </div>
        );
      })}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" size="sm" className="min-h-9" disabled={mutation.isPending}>
          {t("save")}
        </Button>
        <Button type="button" size="sm" variant="outline" className="min-h-9" onClick={onDone}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}

function SectionCard({ section }: { section: SectionName }) {
  const t = useTranslations("candidate.profile");
  const client = useQueryClient();
  const rows = useSection<Record<string, unknown>>(section);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const remove = useMutation({
    mutationFn: (id: string) => candidateApi.remove(section, id),
    onSuccess: () => client.invalidateQueries({ queryKey: candidateKeys.profile }),
  });
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>
          <h2 className="text-lg font-semibold">{t(`sections.${section}`)}</h2>
        </CardTitle>
        {editing === null ? (
          <Button type="button" size="sm" variant="outline" onClick={() => setEditing("new")}>
            <Plus aria-hidden="true" />
            {t("add")}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {rows.isPending ? (
          <p className="text-muted-foreground">{t("loading")}</p>
        ) : rows.isError ? (
          <ErrorState error={rows.error} onRetry={() => rows.refetch()} />
        ) : (
          <>
            {rows.data.length === 0 && editing !== "new" ? (
              <p className="text-muted-foreground">{t("emptySection")}</p>
            ) : null}
            <ul className="flex flex-col gap-2">
              {rows.data.map((row) => (
                <li key={String(row.id)}>
                  {editing === row.id ? (
                    <SectionItemForm
                      section={section}
                      initial={row}
                      onDone={() => setEditing(null)}
                    />
                  ) : (
                    <div className="flex items-center justify-between gap-2">
                      <span>{SECTIONS[section].title(row)}</span>
                      <span className="flex gap-1">
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={t("edit", { item: SECTIONS[section].title(row) })}
                          onClick={() => setEditing(String(row.id))}
                        >
                          <Pencil aria-hidden="true" />
                        </Button>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={t("remove", { item: SECTIONS[section].title(row) })}
                          onClick={() => remove.mutate(String(row.id))}
                        >
                          <Trash2 aria-hidden="true" />
                        </Button>
                      </span>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {editing === "new" ? (
              <SectionItemForm section={section} onDone={() => setEditing(null)} />
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function CandidateProfile() {
  const t = useTranslations("candidate.profile");
  const profile = useProfile();
  if (profile.isPending) return <PageSkeleton />;
  if (profile.isError)
    return <ErrorState error={profile.error} onRetry={() => profile.refetch()} />;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <CompletenessMeter profile={profile.data} />
      <DetailsForm key={profile.data.lock_version} profile={profile.data} />
      {(["experiences", "educations", "certifications", "skills", "languages"] as const).map(
        (s) => (
          <SectionCard key={s} section={s} />
        ),
      )}
    </div>
  );
}
