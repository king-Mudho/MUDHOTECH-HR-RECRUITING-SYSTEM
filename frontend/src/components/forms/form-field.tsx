"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, type ComponentProps, type ReactNode } from "react";
import type { FieldError, FieldErrors, FieldValues } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/** Translate a zod/RHF message: our schemas use i18n keys; server messages pass through. */
export function useErrorText() {
  const t = useTranslations("validation");
  return (message: string | undefined): string | undefined => {
    if (!message) return undefined;
    return t.has(message) ? t(message) : message;
  };
}

interface TextFieldProps extends Omit<ComponentProps<typeof Input>, "id"> {
  label: string;
  description?: ReactNode;
  error?: FieldError;
  required?: boolean;
  name: string;
}

/** Labelled input with description + error wired via aria-describedby (docs/08 §5). */
export function TextField({
  label,
  description,
  error,
  required,
  name,
  className,
  ...props
}: TextFieldProps) {
  const id = `field-${name}`; // stable id so the error summary can link to the field
  const tc = useTranslations("common");
  const errorText = useErrorText()(error?.message);
  const descId = description ? `${id}-desc` : undefined;
  const errId = errorText ? `${id}-err` : undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required ? (
          <span className="text-muted-foreground font-normal"> {tc("required")}</span>
        ) : null}
      </Label>
      <Input
        id={id}
        name={name}
        aria-invalid={errorText ? true : undefined}
        aria-describedby={[descId, errId].filter(Boolean).join(" ") || undefined}
        aria-required={required || undefined}
        className="h-10"
        {...props}
      />
      {description ? (
        <p id={descId} className="text-muted-foreground text-xs">
          {description}
        </p>
      ) : null}
      {errorText ? (
        <p id={errId} className="text-destructive text-sm" role="alert">
          {errorText}
        </p>
      ) : null}
    </div>
  );
}

/** Error summary shown at the top of a form after a failed submit, linking to each field. */
export function ErrorSummary<T extends FieldValues>({
  errors,
  formError,
  labels,
  submitCount,
}: {
  errors: FieldErrors<T>;
  formError?: string | null;
  labels: Record<string, string>;
  submitCount: number;
}) {
  const t = useTranslations("forms");
  const translate = useErrorText();
  const ref = useRef<HTMLDivElement>(null);
  const entries = Object.entries(errors).filter(([key]) => key !== "root");
  const hasErrors = entries.length > 0 || !!formError;
  useEffect(() => {
    if (hasErrors && submitCount > 0) ref.current?.focus();
  }, [hasErrors, submitCount]);
  if (!hasErrors) return null;
  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="alert"
      aria-labelledby="error-summary-title"
      className="border-destructive/40 bg-destructive/5 rounded-md border p-3 text-sm"
    >
      <p id="error-summary-title" className="text-destructive font-semibold">
        {t("errorSummaryTitle")}
      </p>
      <ul className="mt-1 list-disc pl-5">
        {formError ? <li>{formError}</li> : null}
        {entries.map(([key, err]) => (
          <li key={key}>
            <a href={`#field-${key}`} className="underline">
              {labels[key] ?? key}: {translate((err as FieldError | undefined)?.message)}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
