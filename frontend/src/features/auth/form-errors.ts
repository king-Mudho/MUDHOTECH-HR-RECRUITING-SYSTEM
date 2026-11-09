import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "@/lib/api-client";

import { AllauthError } from "./allauth";

/**
 * Map server-side errors onto form fields. `fieldMap` translates server param names
 * (e.g. `new_password`) to form field names (e.g. `newPassword`). Returns the form-level message
 * for anything that could not be attached to a field.
 */
export function applyServerErrors<T extends FieldValues>(
  err: unknown,
  setError: UseFormSetError<T>,
  fieldMap: Record<string, Path<T>> = {},
): string | null {
  let fields: Record<string, string[]> = {};
  let fallback: string | null = null;
  if (err instanceof AllauthError) {
    fields = err.fieldErrors();
    fallback = err.message;
  } else if (err instanceof ApiError) {
    fields = err.fieldErrors();
    fallback = err.message;
  } else {
    return "Something went wrong. Please try again.";
  }
  const formMessages: string[] = [];
  for (const [param, messages] of Object.entries(fields)) {
    const field = fieldMap[param];
    if (field) setError(field, { type: "server", message: messages.join(" ") });
    else formMessages.push(...messages);
  }
  if (formMessages.length > 0) return formMessages.join(" ");
  return Object.keys(fields).length > 0 ? null : fallback;
}
