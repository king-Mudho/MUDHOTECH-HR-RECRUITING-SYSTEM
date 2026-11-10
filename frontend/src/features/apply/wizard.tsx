"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, Loader2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { candidateApi, type Application, type Review } from "@/features/candidates/api";
import { candidateKeys, useProfile, useResumes } from "@/features/candidates/hooks";
import { FileUploader } from "@/features/documents/components/file-uploader";
import { ApiError, api, newIdempotencyKey } from "@/lib/api-client";
import type { components } from "@/types/api";

import { visibleKeys, wordCount } from "./visibility";

type PublicJob = components["schemas"]["PublicJobDetail"];
type Question = components["schemas"]["PublicQuestion"];

export const STEPS = ["contact", "profile", "documents", "questions", "review", "done"] as const;
type Step = (typeof STEPS)[number];

const DOC_ROLE: Record<string, string> = {
  cv: "cv",
  cover_letter: "cover_letter",
  certificates: "certificate",
  transcripts: "transcript",
  portfolio: "portfolio",
};

type SaveState = "idle" | "saving" | "saved" | "error";

// ------------------------------------------------------------------------------- shell
function StepHeader({ step, save }: { step: Step; save: SaveState }) {
  const t = useTranslations("apply");
  const index = STEPS.indexOf(step);
  return (
    <div className="bg-background sticky top-14 z-20 -mx-4 flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
      <p className="text-sm font-medium" aria-live="polite">
        {t("stepOf", { n: Math.min(index + 1, 5), total: 5, title: t(`steps.${step}`) })}
      </p>
      <div className="flex items-center gap-3">
        <p
          role="status"
          aria-live="polite"
          className="text-muted-foreground flex items-center gap-1 text-xs"
        >
          {save === "saving" ? (
            <>
              <Loader2 aria-hidden="true" className="size-3 animate-spin" />
              {t("saving")}
            </>
          ) : save === "saved" ? (
            <>
              <Check aria-hidden="true" className="text-success size-3" />
              {t("saved")}
            </>
          ) : save === "error" ? (
            <>
              <CircleAlert aria-hidden="true" className="text-destructive size-3" />
              {t("notSaved")}
            </>
          ) : null}
        </p>
        {step !== "done" ? (
          <Link href="/candidate/dashboard" className="text-sm underline">
            {t("saveExit")}
          </Link>
        ) : null}
      </div>
    </div>
  );
}

function StepFrame({
  title,
  children,
  focusKey,
}: {
  title: string;
  children: ReactNode;
  focusKey: string;
}) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    ref.current?.focus(); // move focus to the new step for keyboard and screen-reader users
  }, [focusKey]);
  return (
    <section aria-labelledby={`step-${focusKey}`} className="flex flex-col gap-4">
      <h2
        id={`step-${focusKey}`}
        ref={ref}
        tabIndex={-1}
        className="text-xl font-semibold outline-none"
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function Nav({
  onBack,
  onNext,
  nextLabel,
  busy,
}: {
  onBack?: () => void;
  onNext: () => void;
  nextLabel?: string;
  busy?: boolean;
}) {
  const t = useTranslations("apply");
  return (
    <div className="mt-2 flex justify-between gap-2 border-t pt-4">
      {onBack ? (
        <Button type="button" variant="outline" className="min-h-11" onClick={onBack}>
          {t("back")}
        </Button>
      ) : (
        <span />
      )}
      <Button type="button" className="min-h-11" onClick={onNext} disabled={busy}>
        {nextLabel ?? t("continue")}
      </Button>
    </div>
  );
}

// ------------------------------------------------------------------------------- steps
function ContactStep({
  app,
  onSave,
}: {
  app: Application;
  onSave: (contact: Record<string, string>) => Promise<boolean>;
}) {
  const t = useTranslations("apply.contact");
  const profile = useProfile();
  const [values, setValues] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const contact = (app.contact ?? {}) as Record<string, string>;
  const current = values ?? {
    first_name: contact.first_name ?? profile.data?.first_name ?? "",
    last_name: contact.last_name ?? profile.data?.last_name ?? "",
    preferred_name: contact.preferred_name ?? profile.data?.preferred_name ?? "",
    phone: contact.phone ?? profile.data?.phone_e164 ?? "",
    city: contact.city ?? profile.data?.city ?? "",
  };
  const fields: { key: string; type?: string; auto: string; required?: boolean }[] = [
    { key: "first_name", auto: "given-name", required: true },
    { key: "last_name", auto: "family-name", required: true },
    { key: "preferred_name", auto: "nickname" },
    { key: "phone", type: "tel", auto: "tel" },
    { key: "city", auto: "address-level2" },
  ];
  return (
    <>
      <p className="text-muted-foreground text-sm">
        {t("intro", { email: profile.data?.email ?? "" })}
      </p>
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => (
          <div key={f.key} className="flex flex-col gap-1.5">
            <Label htmlFor={`contact-${f.key}`}>
              {t(f.key)}
              {f.required ? (
                <span className="text-muted-foreground font-normal"> {t("required")}</span>
              ) : null}
            </Label>
            <Input
              id={`contact-${f.key}`}
              type={f.type ?? "text"}
              autoComplete={f.auto}
              aria-required={f.required || undefined}
              className="h-11"
              value={current[f.key] ?? ""}
              onChange={(e) => setValues({ ...current, [f.key]: e.target.value })}
            />
          </div>
        ))}
      </div>
      <section
        aria-labelledby="privacy-notice"
        className="bg-muted/40 rounded-lg border p-4 text-sm"
      >
        <h3 id="privacy-notice" className="font-semibold">
          {t("privacyTitle")}
        </h3>
        <p className="mt-1 whitespace-pre-line">
          {app.notices.privacy_notice || t("privacyDefault")}
        </p>
      </section>
      <Nav
        onNext={async () => {
          if (!current.first_name.trim() || !current.last_name.trim()) {
            setError(t("nameRequired"));
            return;
          }
          setError(null);
          if (!(await onSave(current))) setError(t("saveFailed"));
        }}
      />
    </>
  );
}

function ProfileStep({ onBack, onNext }: { onBack: () => void; onNext: () => void }) {
  const t = useTranslations("apply.profile");
  const profile = useProfile();
  if (!profile.data) return <PageSkeleton rows={2} />;
  const p = profile.data;
  return (
    <>
      <p className="text-muted-foreground text-sm">{t("intro")}</p>
      <dl className="grid gap-2 rounded-lg border p-4 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-muted-foreground">{t("headline")}</dt>
        <dd>{p.headline || t("notAdded")}</dd>
        <dt className="text-muted-foreground">{t("summary")}</dt>
        <dd className="line-clamp-3">{p.summary || t("notAdded")}</dd>
        <dt className="text-muted-foreground">{t("completeness")}</dt>
        <dd>{t("percent", { value: p.profile_completeness })}</dd>
      </dl>
      <p className="text-sm">
        <Link href="/candidate/profile" className="underline">
          {t("edit")}
        </Link>{" "}
        <span className="text-muted-foreground">{t("editHelp")}</span>
      </p>
      <Nav onBack={onBack} onNext={onNext} />
    </>
  );
}

function DocumentsStep({
  job,
  review,
  onSave,
  onBack,
}: {
  job: PublicJob;
  review: Review | undefined;
  onSave: (
    docs: { document_id: string; role: string; required_doc_key: string }[],
  ) => Promise<boolean>;
  onBack: () => void;
}) {
  const t = useTranslations("apply.documents");
  const tc = useTranslations("jobs.choices.documents");
  const resumes = useResumes();
  const required = job.required_documents.length ? job.required_documents : ["cv"];
  const [chosen, setChosen] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const attached: Record<string, string> = {};
  for (const d of review?.documents ?? []) attached[d.required_doc_key || d.role] = d.document;
  const defaultCv = resumes.data?.find((r) => r.is_default)?.id;
  const current = chosen ?? { ...(defaultCv ? { cv: defaultCv } : {}), ...attached };
  const usable = (resumes.data ?? []).filter(
    (r) => !["infected", "rejected", "error"].includes(r.scan_status),
  );
  return (
    <>
      <p className="text-muted-foreground text-sm">{t("intro")}</p>
      {required.map((key) => (
        <fieldset key={key} className="flex flex-col gap-3 rounded-lg border p-4">
          <legend className="px-1 font-medium">
            {tc.has(key) ? tc(key) : key}{" "}
            <span className="text-muted-foreground text-sm font-normal">{t("required")}</span>
          </legend>
          {key === "cv" && usable.length > 0 ? (
            <div className="flex flex-col gap-2" role="radiogroup" aria-label={t("chooseCv")}>
              {usable.map((r) => (
                <label key={r.id} className="flex min-h-6 items-center gap-2 text-sm">
                  <input
                    type="radio"
                    className="size-4"
                    name="cv-choice"
                    checked={current.cv === r.id}
                    onChange={() => setChosen({ ...current, cv: r.id })}
                  />
                  {r.original_filename}
                  {r.scan_status === "pending" ? (
                    <span className="text-muted-foreground text-xs">({t("checking")})</span>
                  ) : null}
                </label>
              ))}
            </div>
          ) : null}
          <FileUploader
            purpose={key === "cv" ? "cv" : "supporting"}
            label={key === "cv" && usable.length > 0 ? t("uploadAnother") : t("upload")}
            onUploaded={(doc) => setChosen({ ...current, [key]: doc.id })}
          />
          {current[key] && key !== "cv" ? (
            <p className="text-success text-sm">{t("attached")}</p>
          ) : null}
        </fieldset>
      ))}
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
      <Nav
        onBack={onBack}
        onNext={async () => {
          const missing = required.filter((k) => !current[k]);
          if (missing.length) {
            setError(
              t("missing", { list: missing.map((k) => (tc.has(k) ? tc(k) : k)).join(", ") }),
            ); // EC-APP-10
            return;
          }
          setError(null);
          const docs = required.map((k) => ({
            document_id: current[k]!,
            role: DOC_ROLE[k] ?? "other",
            required_doc_key: k,
          }));
          if (!(await onSave(docs))) setError(t("saveFailed"));
        }}
      />
    </>
  );
}

function QuestionInput({
  q,
  value,
  onChange,
  error,
}: {
  q: Question;
  value: unknown;
  onChange: (v: unknown) => void;
  error?: string;
}) {
  const t = useTranslations("apply.questions");
  const id = `q-${q.key}`;
  const descIds =
    [q.help_text ? `${id}-help` : null, error ? `${id}-err` : null].filter(Boolean).join(" ") ||
    undefined;
  const limit = Number((q.config as Record<string, unknown>).word_limit ?? 0);
  const common = {
    id,
    "aria-describedby": descIds,
    "aria-invalid": error ? true : undefined,
    "aria-required": q.required || undefined,
  };
  let control: ReactNode;
  if (q.type === "yes_no" || q.type === "single_choice") {
    const options =
      q.type === "yes_no"
        ? [
            { label: t("yes"), value: "yes" },
            { label: t("no"), value: "no" },
          ]
        : q.options;
    control = (
      <div
        role="radiogroup"
        aria-labelledby={`${id}-label`}
        aria-describedby={descIds}
        className="flex flex-wrap gap-4"
      >
        {options.map((o) => (
          <label key={o.value} className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="radio"
              className="size-5"
              name={id}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
            />
            {o.label}
          </label>
        ))}
      </div>
    );
  } else if (q.type === "multiple_choice") {
    const list = Array.isArray(value) ? (value as string[]) : [];
    control = (
      <div
        role="group"
        aria-labelledby={`${id}-label`}
        aria-describedby={descIds}
        className="flex flex-col gap-2"
      >
        {q.options.map((o) => (
          <label key={o.value} className="flex min-h-6 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-5"
              checked={list.includes(o.value)}
              onChange={(e) =>
                onChange(e.target.checked ? [...list, o.value] : list.filter((v) => v !== o.value))
              }
            />
            {o.label}
          </label>
        ))}
      </div>
    );
  } else if (q.type === "long_text") {
    const text = typeof value === "string" ? value : "";
    control = (
      <>
        <textarea
          {...common}
          rows={5}
          className="border-input bg-background rounded-md border px-3 py-2 text-sm"
          value={text}
          onChange={(e) => onChange(e.target.value)}
        />
        {limit ? (
          <p
            className={
              wordCount(text) > limit ? "text-destructive text-xs" : "text-muted-foreground text-xs"
            }
            aria-live="polite"
          >
            {t("words", { count: wordCount(text), limit })}
          </p>
        ) : null}
      </>
    );
  } else if (q.type === "file_upload") {
    control = (
      <FileUploader
        purpose="supporting"
        label={t("uploadFile")}
        onUploaded={(doc) => onChange(doc.id)}
      />
    );
  } else {
    const numeric = ["number", "scale", "availability", "salary_expectation"].includes(q.type);
    control = (
      <Input
        {...common}
        type={q.type === "date" ? "date" : numeric ? "number" : "text"}
        inputMode={numeric ? "decimal" : undefined}
        className="h-11 sm:max-w-xs"
        value={value === null || value === undefined ? "" : String(value)}
        onChange={(e) =>
          onChange(e.target.value === "" ? null : numeric ? Number(e.target.value) : e.target.value)
        }
      />
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <Label id={`${id}-label`} htmlFor={id}>
        {q.prompt}
        {q.required ? (
          <span className="text-muted-foreground font-normal"> {t("required")}</span>
        ) : null}
      </Label>
      {q.help_text ? (
        <p id={`${id}-help`} className="text-muted-foreground text-xs">
          {q.help_text}
        </p>
      ) : null}
      {control}
      {error ? (
        <p id={`${id}-err`} role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function QuestionsStep({
  questions,
  review,
  onSave,
  onBack,
  onNext,
}: {
  questions: Question[];
  review: Review | undefined;
  onSave: (answers: { key: string; value: unknown }[]) => Promise<ApiError | null>;
  onBack: () => void;
  onNext: () => void;
}) {
  const t = useTranslations("apply.questions");
  const [answers, setAnswers] = useState<Record<string, unknown>>(() => ({
    ...(review?.answers ?? {}),
  }));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const dirty = useRef(false);
  const shown = visibleKeys(questions, answers);
  const save = useCallback(async () => {
    const err = await onSave(Object.entries(answers).map(([key, value]) => ({ key, value })));
    dirty.current = false;
    const fe: Record<string, string> = {};
    if (err) for (const [k, v] of Object.entries(err.fieldErrors())) fe[k] = v.join(" ");
    setErrors(fe);
    return !err;
  }, [answers, onSave]);
  useEffect(() => {
    if (!dirty.current) return;
    const id = setTimeout(() => void save(), 800); // debounced autosave (EC-APP-20: small payloads)
    return () => clearTimeout(id);
  }, [answers, save]);
  if (questions.length === 0)
    return (
      <>
        <p className="text-muted-foreground text-sm">{t("none")}</p>
        <Nav onBack={onBack} onNext={onNext} />
      </>
    );
  return (
    <>
      <p className="text-muted-foreground text-sm">{t("intro")}</p>
      <div aria-live="polite" className="flex flex-col gap-6">
        {questions
          .filter((q) => shown.includes(q.key))
          .map((q) => (
            <QuestionInput
              key={q.key}
              q={q}
              value={answers[q.key]}
              error={errors[q.key]}
              onChange={(v) => {
                dirty.current = true;
                setAnswers((prev) => ({ ...prev, [q.key]: v }));
              }}
            />
          ))}
      </div>
      <Nav
        onBack={onBack}
        onNext={async () => {
          if (await save()) onNext();
        }}
      />
    </>
  );
}

function ReviewStep({
  job,
  app,
  review,
  questions,
  goTo,
  onSubmitted,
}: {
  job: PublicJob;
  app: Application;
  review: Review | undefined;
  questions: Question[];
  goTo: (s: Step) => void;
  onSubmitted: (reference: string) => void;
}) {
  const t = useTranslations("apply.review");
  const tc = useTranslations("jobs.choices.documents");
  const router = useRouter();
  const [privacy, setPrivacy] = useState(false);
  const [objects, setObjects] = useState(false);
  const [error, setError] = useState<{
    title: string;
    body: string;
    link?: { href: string; label: string };
  } | null>(null);
  const [missing, setMissing] = useState<{ step: string; code: string; key: string }[]>([]);
  const keyRef = useRef(newIdempotencyKey()); // one key per attempt session (EC-APP-04)
  const submit = useMutation({
    mutationFn: () =>
      candidateApi.submit(
        app.id,
        { accept_privacy: privacy, objects_to_automated_processing: objects },
        keyRef.current,
      ),
    onSuccess: (res) => onSubmitted(res.reference),
    onError: (err) => {
      keyRef.current = newIdempotencyKey();
      if (!(err instanceof ApiError))
        return setError({ title: t("failedTitle"), body: t("failed") });
      if (err.status === 401) return router.push(`/login?next=/apply/${job.id}`); // EC-APP-06
      const code = err.code;
      if (code === "submit_blocked" || code === "email_unverified") {
        setMissing(((err.details.missing ?? []) as typeof missing) || []);
      }
      if (code === "conflict.duplicate_application")
        setError({
          title: t("duplicateTitle"),
          body: t("duplicate"),
          link: {
            href: `/candidate/applications/${String(err.details.application_id ?? "")}`,
            label: t("openExisting"),
          },
        });
      else if (code === "conflict.not_draft")
        setError({
          title: t("duplicateTitle"),
          body: t("alreadySubmitted"),
          link: { href: `/candidate/applications/${app.id}`, label: t("openExisting") },
        });
      else if (
        [
          "deadline_passed",
          "job_paused",
          "job_not_accepting",
          "org_suspended",
          "email_unverified",
        ].includes(code)
      )
        setError({ title: t(`errors.${code}.title`), body: t(`errors.${code}.body`) }); // EC-APP-14/19
      else setError({ title: t("failedTitle"), body: err.message });
    },
  });
  const blocking = missing.length ? missing : (review?.missing ?? []);
  const labelFor = (m: { code: string; key: string }) => {
    if (m.code === "document_required")
      return t("missingDoc", { doc: tc.has(m.key) ? tc(m.key) : m.key });
    if (m.code === "answer_required")
      return t("missingAnswer", {
        question: questions.find((q) => q.key === m.key)?.prompt ?? m.key,
      });
    if (m.code === "email_unverified") return t("codes.emailUnverified");
    if (m.code === "document_rejected") return t("codes.documentNotAccepted");
    return t("codes.other");
  };
  const stepOf: Record<string, Step> = {
    contact: "contact",
    documents: "documents",
    questions: "questions",
  };
  return (
    <>
      {error ? (
        <Alert variant="destructive" role="alert">
          <AlertTitle>{error.title}</AlertTitle>
          <AlertDescription>
            {error.body}
            {error.link ? (
              <>
                {" "}
                <Link href={error.link.href} className="underline">
                  {error.link.label}
                </Link>
              </>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}
      {blocking.length > 0 ? (
        <section
          aria-labelledby="still-needed"
          className="border-destructive/40 rounded-lg border p-4 text-sm"
        >
          <h3 id="still-needed" className="font-semibold">
            {t("stillNeeded")}
          </h3>
          <ul className="mt-2 flex flex-col gap-1">
            {blocking.map((m) => (
              <li key={`${m.code}-${m.key}`} className="flex flex-wrap items-center gap-2">
                {labelFor(m)}
                {stepOf[m.step] ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="link"
                    className="h-auto p-0"
                    onClick={() => goTo(stepOf[m.step]!)}
                  >
                    {t("fix")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section aria-labelledby="summary" className="rounded-lg border p-4 text-sm">
        <h3 id="summary" className="font-semibold">
          {t("summary")}
        </h3>
        <dl className="mt-2 grid gap-1 sm:grid-cols-[12rem_1fr]">
          <dt className="text-muted-foreground">{t("vacancy")}</dt>
          <dd>
            {job.title} · {job.organisation.name}
          </dd>
          <dt className="text-muted-foreground">{t("documents")}</dt>
          <dd>{(review?.documents ?? []).map((d) => d.filename).join(", ") || "—"}</dd>
          {Object.entries(review?.answers ?? {}).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">
                {questions.find((q) => q.key === k)?.prompt ?? k}
              </dt>
              <dd>{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section aria-labelledby="extracted" className="bg-muted/40 rounded-lg border p-4 text-sm">
        <h3 id="extracted" className="font-semibold">
          {t("extractedTitle")}
        </h3>
        <p className="text-muted-foreground mt-1">{t("extractedSoon")}</p>
      </section>
      <fieldset className="flex flex-col gap-3 rounded-lg border p-4 text-sm">
        <legend className="px-1 font-semibold">{t("consents")}</legend>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-0.5 size-5"
            checked={privacy}
            onChange={(e) => setPrivacy(e.target.checked)}
            aria-required="true"
          />
          <span>
            {t("privacy", { company: job.organisation.name })}{" "}
            <span className="text-muted-foreground">{t("requiredMark")}</span>
          </span>
        </label>
        <p className="text-muted-foreground">
          {t("aiNotice")}{" "}
          <Link href="/how-we-use-ai" target="_blank" className="underline">
            {t("aiNoticeLink")}
          </Link>
        </p>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-0.5 size-5"
            checked={objects}
            onChange={(e) => setObjects(e.target.checked)}
          />
          <span>{t("object")}</span>
        </label>
      </fieldset>
      <div className="mt-2 flex justify-between gap-2 border-t pt-4">
        <Button
          type="button"
          variant="outline"
          className="min-h-11"
          onClick={() => goTo("questions")}
        >
          {t("back")}
        </Button>
        <Button
          type="button"
          className="min-h-11"
          disabled={!privacy || submit.isPending}
          onClick={() => submit.mutate()}
        >
          {submit.isPending ? t("submitting") : t("submit")}
        </Button>
      </div>
    </>
  );
}

function DoneStep({
  app,
  reference,
  job,
}: {
  app: Application;
  reference: string;
  job: PublicJob;
}) {
  const t = useTranslations("apply.done");
  return (
    <>
      <Alert role="status">
        <AlertTitle>{t("title")}</AlertTitle>
        <AlertDescription>{t("reference", { reference })}</AlertDescription>
      </Alert>
      <section aria-labelledby="next" className="text-sm">
        <h3 id="next" className="font-semibold">
          {t("nextTitle")}
        </h3>
        <ol className="mt-2 list-decimal space-y-1 pl-5">
          <li>{t("next1")}</li>
          <li>{t("next2", { company: job.organisation.name })}</li>
          <li>{t("next3")}</li>
        </ol>
      </section>
      <div className="flex flex-wrap gap-2">
        <Button asChild className="min-h-11">
          <Link href={`/candidate/applications/${app.id}`}>{t("track")}</Link>
        </Button>
        <Button asChild variant="outline" className="min-h-11">
          <Link href="/jobs">{t("more")}</Link>
        </Button>
      </div>
    </>
  );
}

// ------------------------------------------------------------------------------ wizard
export function ApplyWizard({ jobId }: { jobId: string }) {
  const t = useTranslations("apply");
  const format = useFormatter();
  const router = useRouter();
  const params = useSearchParams();
  const client = useQueryClient();
  const job = useQuery({
    queryKey: ["jobs", "public", jobId],
    queryFn: () => api.get<PublicJob>(`/jobs/${jobId}/`),
  });
  const questions = useQuery({
    queryKey: ["jobs", "public", jobId, "questions"],
    queryFn: () => api.get<Question[]>(`/jobs/${jobId}/questions/`),
  });
  const started = useQuery({
    queryKey: ["apply", jobId],
    queryFn: () => {
      const source: Record<string, string> = {};
      for (const k of ["utm_source", "utm_medium", "utm_campaign"])
        if (params.get(k)) source[k] = params.get(k)!.slice(0, 100);
      return candidateApi.start(jobId, Object.keys(source).length ? source : undefined); // server: direct (EC-APP-23)
    },
    retry: false,
    staleTime: Infinity,
  });
  const app = started.data;
  const review = useQuery({
    queryKey: candidateKeys.review(app?.id ?? ""),
    queryFn: () => candidateApi.review(app!.id),
    enabled: !!app && app.status === "draft",
  });
  const appRef = useRef<Application | undefined>(app);
  useEffect(() => {
    appRef.current = app;
  }, [app]);
  const [step, setStep] = useState<Step | null>(null);
  const [save, setSave] = useState<SaveState>("idle");
  const [reference, setReference] = useState<string | null>(null);
  const current: Step =
    step ?? (app ? STEPS[Math.min(Math.max(app.last_step, 1), 5) - 1]! : "contact");

  const handle = async <T,>(fn: () => Promise<T>): Promise<T | ApiError> => {
    setSave("saving");
    try {
      const out = await fn();
      setSave("saved");
      return out;
    } catch (err) {
      setSave("error");
      if (err instanceof ApiError && err.status === 401) router.push(`/login?next=/apply/${jobId}`); // EC-APP-06
      if (err instanceof ApiError && err.code === "conflict.stale_version") {
        await client.invalidateQueries({ queryKey: ["apply", jobId] }); // EC-APP-19: reload latest
      }
      return err instanceof ApiError ? err : new ApiError(0, "unknown", String(err));
    }
  };
  const patch = async (data: { last_step?: number; contact?: Record<string, string> }) => {
    const latest = appRef.current!;
    const res = await handle(() =>
      candidateApi.updateDraft(latest.id, { lock_version: latest.lock_version, ...data }),
    );
    if (!(res instanceof ApiError)) {
      appRef.current = res;
      client.setQueryData(["apply", jobId], res);
    }
    return !(res instanceof ApiError);
  };
  const syncApp = (latest: Application) => {
    appRef.current = latest;
    client.setQueryData(["apply", jobId], latest);
  };
  const goTo = (s: Step) => {
    setStep(s);
    if (s !== "done") void patch({ last_step: STEPS.indexOf(s) + 1 });
  };

  if (job.isPending || started.isPending || questions.isPending) return <PageSkeleton />;
  if (job.isError) return <ErrorState error={job.error} onRetry={() => job.refetch()} />;
  if (started.isError) {
    const err = started.error;
    if (err instanceof ApiError && err.code === "conflict.duplicate_application")
      return (
        <Alert role="alert">
          <AlertTitle>{t("duplicateTitle")}</AlertTitle>
          <AlertDescription>
            {t("duplicate")}{" "}
            <Link
              href={`/candidate/applications/${String(err.details.application_id ?? "")}`}
              className="underline"
            >
              {t("openExisting")}
            </Link>
          </AlertDescription>
        </Alert>
      );
    if (err instanceof ApiError && ["deadline_passed", "job_not_accepting"].includes(err.code))
      return (
        <Alert role="alert">
          <AlertTitle>{t("closedTitle")}</AlertTitle>
          <AlertDescription>
            {t("closed")}{" "}
            <Link href="/jobs" className="underline">
              {t("browse")}
            </Link>
          </AlertDescription>
        </Alert>
      );
    return <ErrorState error={err} onRetry={() => started.refetch()} />;
  }
  const j = job.data;
  const a = app!;
  if (a.status !== "draft" && !reference)
    return (
      <Alert role="status">
        <AlertDescription>
          {t("alreadySubmitted")}{" "}
          <Link href={`/candidate/applications/${a.id}`} className="underline">
            {t("openExisting")}
          </Link>
        </AlertDescription>
      </Alert>
    );
  const shownStep: Step = reference ? "done" : current;
  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-muted-foreground text-sm">{t("applyingFor")}</p>
        <h1 className="text-2xl font-semibold">{j.title}</h1>
        <p className="text-muted-foreground text-sm">
          {j.organisation.name}
          {j.closes_at
            ? ` · ${t("closes", { date: format.dateTime(new Date(j.closes_at), { dateStyle: "medium", timeStyle: "short", timeZone: j.timezone }), tz: j.timezone })}`
            : ""}
        </p>
      </div>
      <StepHeader step={shownStep} save={save} />
      <StepFrame title={t(`steps.${shownStep}`)} focusKey={shownStep}>
        {shownStep === "contact" ? (
          <ContactStep
            app={a}
            onSave={async (contact) =>
              (await patch({ contact, last_step: 2 })) && (setStep("profile"), true)
            }
          />
        ) : shownStep === "profile" ? (
          <ProfileStep onBack={() => goTo("contact")} onNext={() => goTo("documents")} />
        ) : shownStep === "documents" ? (
          <DocumentsStep
            job={j}
            review={review.data}
            onBack={() => goTo("profile")}
            onSave={async (docs) => {
              const res = await handle(() => candidateApi.setDocuments(a.id, docs));
              if (res instanceof ApiError) return false;
              client.setQueryData(candidateKeys.review(a.id), res);
              syncApp(res.application); // documents/answers bump lock_version
              goTo("questions");
              return true;
            }}
          />
        ) : shownStep === "questions" ? (
          <QuestionsStep
            questions={questions.data ?? []}
            review={review.data}
            onBack={() => goTo("documents")}
            onNext={() => goTo("review")}
            onSave={async (answers) => {
              const res = await handle(() => candidateApi.setAnswers(a.id, answers));
              if (res instanceof ApiError) return res;
              client.setQueryData(candidateKeys.review(a.id), res);
              syncApp(res.application); // documents/answers bump lock_version
              return null;
            }}
          />
        ) : shownStep === "review" ? (
          <ReviewStep
            job={j}
            app={a}
            review={review.data}
            questions={questions.data ?? []}
            goTo={goTo}
            onSubmitted={(ref) => {
              setReference(ref);
              void client.invalidateQueries({ queryKey: candidateKeys.applications });
            }}
          />
        ) : (
          <DoneStep app={a} reference={reference ?? a.reference ?? ""} job={j} />
        )}
      </StepFrame>
    </div>
  );
}

/** Route wrapper that reads the dynamic `[jobId]` segment on the client. */
export function ApplyWizardRoute() {
  const { jobId } = useParams<{ jobId: string }>();
  return <ApplyWizard jobId={jobId} />;
}
