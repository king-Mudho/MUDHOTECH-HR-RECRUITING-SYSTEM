"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

import { rubricFromJob, rubricProblems, rubricTotal, type RubricRow } from "../schemas";
import { useAutosave } from "./use-autosave";
import { StepFooter, useWizard } from "./wizard-context";

/**
 * Weighted rubric (FR-M04-04, EC-JOB-02). Weights must total exactly 100; the running total is
 * announced politely. Kept as local state: the rows are fixed (five categories) and the server
 * re-validates on save.
 */
export function RubricStep() {
  const t = useTranslations("jobs.rubric");
  const tc = useTranslations("jobs.choices.rubric");
  const { job, api, save } = useWizard();
  const [rows, setRows] = useState<RubricRow[]>(() => rubricFromJob(job));
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const total = rubricTotal(rows);
  const problems = rubricProblems(rows);

  const update = (i: number, patch: Partial<RubricRow>) => {
    setRows((prev) => prev.map((r, j) => (j === i ? { ...r, ...patch } : r)));
    setDirty(true);
  };
  const persist = async (): Promise<boolean> => {
    if (problems.length > 0) {
      setError(t(`problems.${problems[0]}`));
      return false;
    }
    setError(null);
    const result = await save((lock) =>
      api.setRubric(
        job.id,
        rows.map((r) => ({ key: r.key, label: r.label, weight: r.weight, bands: r.bands })),
        lock,
      ),
    );
    if (result instanceof ApiError) {
      if (result.code !== "conflict.stale_version") setError(result.message);
      return false;
    }
    setDirty(false);
    return true;
  };
  useAutosave(rows, dirty && problems.length === 0, () => void persist());

  return (
    <form
      method="post"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void persist();
      }}
      className="flex flex-col gap-4"
    >
      <div>
        <h2 className="text-lg font-semibold">{t("title")}</h2>
        <p className="text-muted-foreground text-sm">{t("intro")}</p>
      </div>
      <p
        aria-live="polite"
        className={cn("text-sm font-medium", total === 100 ? "text-success" : "text-destructive")}
        data-testid="rubric-total"
      >
        {t("total", { total })}{" "}
        {total === 100 ? t("totalOk") : t("totalNeeds", { diff: 100 - total })}
      </p>
      {error ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {rows.map((row, i) => (
        <Card key={row.key}>
          <CardContent className="flex flex-col gap-3 pt-4">
            <div className="flex flex-wrap items-end gap-4">
              <div className="flex min-w-48 flex-1 flex-col gap-1.5">
                <Label htmlFor={`weight-range-${row.key}`}>{tc(row.key)}</Label>
                <input
                  id={`weight-range-${row.key}`}
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={row.weight}
                  onChange={(e) => update(i, { weight: Number(e.target.value) })}
                  aria-valuetext={t("percent", { value: row.weight })}
                  className="accent-primary h-6"
                />
              </div>
              <div className="flex w-24 flex-col gap-1.5">
                <Label htmlFor={`weight-${row.key}`}>{t("weight")}</Label>
                <Input
                  id={`weight-${row.key}`}
                  type="number"
                  min={0}
                  max={100}
                  value={row.weight}
                  onChange={(e) =>
                    update(i, {
                      weight: Math.max(0, Math.min(100, Math.round(Number(e.target.value) || 0))),
                    })
                  }
                  className="h-10"
                />
              </div>
            </div>
            <details>
              <summary className="cursor-pointer text-sm font-medium">{t("bands")}</summary>
              <div className="mt-2 flex flex-col gap-2">
                {row.bands.map((b, bi) => (
                  <div key={bi} className="flex items-center gap-2">
                    <span className="w-12 text-sm tabular-nums" aria-hidden="true">
                      {b.score}
                    </span>
                    <Label htmlFor={`band-${row.key}-${bi}`} className="sr-only">
                      {t("bandLabel", { score: b.score })}
                    </Label>
                    <Input
                      id={`band-${row.key}-${bi}`}
                      value={b.descriptor}
                      className="h-10"
                      onChange={(e) =>
                        update(i, {
                          bands: row.bands.map((x, j) =>
                            j === bi ? { ...x, descriptor: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </div>
                ))}
              </div>
            </details>
          </CardContent>
        </Card>
      ))}
      <div>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            const even = [35, 25, 20, 10, 10];
            setRows((prev) => prev.map((r, i) => ({ ...r, weight: even[i] ?? 0 })));
            setDirty(true);
          }}
        >
          {t("resetDefaults")}
        </Button>
      </div>
      <StepFooter step="rubric" onSave={persist} />
    </form>
  );
}
