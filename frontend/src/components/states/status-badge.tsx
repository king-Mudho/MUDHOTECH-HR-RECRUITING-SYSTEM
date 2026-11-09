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
  pending_verification: "warning",
  active: "success",
  suspended: "danger",
  deactivated: "neutral",
};

// Label text always uses the foreground colour (WCAG AA contrast on the tinted background);
// the tone is carried by the tint, the border and the shaped dot.
const TONE_CLASSES: Record<StatusTone, string> = {
  neutral: "bg-muted text-foreground border-border",
  info: "bg-info/10 text-foreground border-info/40",
  success: "bg-success/10 text-foreground border-success/40",
  warning: "bg-warning/10 text-foreground border-warning/40",
  danger: "bg-destructive/10 text-foreground border-destructive/40",
  brand: "bg-brand-accent/10 text-foreground border-brand-accent/40",
};

const DOT_COLOUR: Record<StatusTone, string> = {
  neutral: "bg-muted-foreground",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-destructive",
  brand: "bg-brand-accent",
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
      <span aria-hidden="true" className={cn("size-2", DOT_COLOUR[tone], DOT_SHAPE[tone])} />
      {label}
    </span>
  );
}
