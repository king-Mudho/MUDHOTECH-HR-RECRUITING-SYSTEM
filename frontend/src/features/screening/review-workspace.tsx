"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { Evaluation } from "./api";
import { EvaluationPanel } from "./components";
import { EvidenceViewer } from "./evidence-viewer";

const ORDER_KEY = (jobId: string) => `mhrs:applicants:${jobId}`;

/** Remembered list order from the applicants table, for j/k navigation (per browser tab). */
export function rememberOrder(jobId: string, ids: string[]) {
  try {
    sessionStorage.setItem(ORDER_KEY(jobId), JSON.stringify(ids));
  } catch {
    // storage blocked: navigation shortcuts are a convenience only
  }
}

function readOrder(jobId: string): string[] {
  try {
    const raw = sessionStorage.getItem(ORDER_KEY(jobId));
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function typing(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

/** j / k move to the next / previous applicant of the list the reviewer came from. */
export function useApplicantKeys(jobId: string, appId: string) {
  const router = useRouter();
  const ids = useMemo(() => readOrder(jobId), [jobId]);
  const index = ids.indexOf(appId);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return;
      if (e.key !== "j" && e.key !== "k") return;
      const next = ids[index + (e.key === "j" ? 1 : -1)];
      if (index >= 0 && next) {
        e.preventDefault();
        router.push(`/hr/applications/${next}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ids, index, router]);
  return index >= 0 ? { index, total: ids.length } : null;
}

/** Evidence on the left, AI-assisted evaluation on the right; picking a criterion highlights it. */
export function ReviewWorkspace({ appId, jobId }: { appId: string; jobId: string }) {
  const t = useTranslations("screening.review");
  const [active, setActive] = useState<string | null>(null);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const position = useApplicantKeys(jobId, appId);
  const onLoaded = useCallback((evaluation: Evaluation | null) => {
    setTitles(
      Object.fromEntries((evaluation?.criteria ?? []).map((c) => [c.criterion_id, c.title])),
    );
  }, []);
  return (
    <div className="flex flex-col gap-2">
      {position ? (
        <p className="text-muted-foreground text-xs">
          {t("position", { index: position.index + 1, total: position.total })}
        </p>
      ) : null}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 [&>*]:min-w-0">
        <EvidenceViewer appId={appId} activeCriterion={active} criterionTitles={titles} />
        <EvaluationPanel appId={appId} active={active} onSelect={setActive} onLoaded={onLoaded} />
      </div>
    </div>
  );
}
