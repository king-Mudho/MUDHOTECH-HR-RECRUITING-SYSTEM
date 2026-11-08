"use client";

import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger" | "brand";

/**
 * Status -> tone. Colours are consistent across the app and are never the only signal:
 * every badge renders the human-readable label (and a shape-coded dot).
 * Candidates are never "rejected" - the label is "Not selected".
 */
export const STATUS_TONES: Record<string, StatusTone> = {
  draft: "neutral",
  submitted: "info",
  under_review: "info",
  processing_error: "danger",
  clarification_requested: "warning",
  shortlisted: "success",
  not_selected: "neutral",
  on_hold: "warning",
  withdrawn: "neutral",
  interview: "brand",
  offer: "brand",
  hired: "success",
  published: "success",
  closed: "neutral",
  paused: "warning",
  archived: "neutral",
};

const TONE_CLASSES: Record<StatusTone, string> = {
  neutral: "bg-muted text-foreground border-border",
  info: "bg-info/10 text-info border-info/30",
  success: "bg-success/10 text-success border-success/30",
  warning: "bg-warning/10 text-warning border-warning/30",
  danger: "bg-destructive/10 text-destructive border-destructive/30",
  brand: "bg-brand-accent/10 text-brand-accent border-brand-accent/30",
};

const DOT_SHAPE: Record<StatusTone, string> = {
  neutral: "rounded-full",
  info: "rounded-full",
  success: "rounded-full",
  warning: "rotate-45 rounded-[1px]",
  danger: "rounded-[1px]",
  brand: "rounded-full",
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const t = useTranslations("status");
  const tone = STATUS_TONES[status] ?? "neutral";
  const label = t.has(status) ? t(status) : status.replaceAll("_", " ");
  return (
    <span
      data-status={status}
      data-tone={tone}
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium",
        TONE_CLASSES[tone],
        className,
      )}
    >
      <span aria-hidden="true" className={cn("size-1.5 bg-current", DOT_SHAPE[tone])} />
      {label}
    </span>
  );
}
