"use client";

import { useTranslations } from "next-intl";
import { createContext, useContext } from "react";

import { Button } from "@/components/ui/button";
import type { ApiError } from "@/lib/api-client";

import type { JobDetail, jobsApi } from "../api";

export const STEPS = ["details", "requirements", "questions", "rubric", "preview"] as const;
export type Step = (typeof STEPS)[number];

export type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; at: number }
  | { kind: "error"; message: string }
  | { kind: "conflict" };

export interface WizardContextValue {
  job: JobDetail;
  api: ReturnType<typeof jobsApi>;
  role: string | null;
  /** Run a save with the current lock version; updates the cache and the save indicator. */
  save: (fn: (lockVersion: number) => Promise<JobDetail>) => Promise<JobDetail | ApiError>;
  saveState: SaveState;
  goTo: (step: Step) => void;
  /** Bumped when the user reloads after a conflict so steps reset their forms. */
  resetToken: number;
}

export const WizardContext = createContext<WizardContextValue | null>(null);

export function useWizard(): WizardContextValue {
  const ctx = useContext(WizardContext);
  if (!ctx) throw new Error("useWizard must be used inside JobWizard");
  return ctx;
}

/** Next/back footer used by each step. */
export function StepFooter({
  step,
  onSave,
  saving,
  saveLabel,
}: {
  step: Step;
  onSave?: () => Promise<boolean>;
  saving?: boolean;
  saveLabel?: string;
}) {
  const t = useTranslations("jobs.wizard");
  const { goTo } = useWizard();
  const index = STEPS.indexOf(step);
  const prev = STEPS[index - 1];
  const next = STEPS[index + 1];
  return (
    <div className="mt-6 flex flex-wrap justify-between gap-2 border-t pt-4">
      {prev ? (
        <Button type="button" variant="outline" className="min-h-10" onClick={() => goTo(prev)}>
          {t("back")}
        </Button>
      ) : (
        <span />
      )}
      <div className="flex gap-2">
        {onSave ? (
          <Button
            type="button"
            variant="outline"
            className="min-h-10"
            disabled={saving}
            onClick={() => void onSave()}
          >
            {saveLabel ?? t("save.button")}
          </Button>
        ) : null}
        {next ? (
          <Button
            type="button"
            className="min-h-10"
            disabled={saving}
            onClick={async () => {
              if (!onSave || (await onSave())) goTo(next);
            }}
          >
            {t("saveAndContinue")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
