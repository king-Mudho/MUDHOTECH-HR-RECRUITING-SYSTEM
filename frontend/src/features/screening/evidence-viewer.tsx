"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Button } from "@/components/ui/button";
import { documentsApi } from "@/features/documents/api";
import { useJobsContext } from "@/features/jobs/hooks";
import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

type EvidenceText = components["schemas"]["EvidenceText"];
type Doc = EvidenceText["documents"][number];
type Highlight = Doc["highlights"][number];

/** Splits page text into plain and highlighted segments (overlaps merge into one mark). */
function segments(text: string, marks: Highlight[]) {
  const sorted = [...marks].sort((a, b) => a.start - b.start);
  const out: { text: string; marks: Highlight[] }[] = [];
  let at = 0;
  for (const m of sorted) {
    const start = Math.max(m.start, at);
    if (m.end <= at) {
      const last = out[out.length - 1];
      if (last && last.marks.length) last.marks.push(m);
      continue;
    }
    if (start > at) out.push({ text: text.slice(at, start), marks: [] });
    out.push({ text: text.slice(start, m.end), marks: [m] });
    at = m.end;
  }
  if (at < text.length) out.push({ text: text.slice(at), marks: [] });
  return out;
}

/** Original PDF rendered by pdf.js into canvases (no scripting, no eval). */
function PdfPages({ documentId }: { documentId: string }) {
  const t = useTranslations("screening.evidence");
  const host = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const el = host.current;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();
        const doc = await pdfjs.getDocument({
          url: documentsApi.downloadUrl(documentId),
          withCredentials: true,
        }).promise;
        for (let n = 1; n <= Math.min(doc.numPages, 10) && !cancelled; n++) {
          const page = await doc.getPage(n);
          const viewport = page.getViewport({ scale: 1.2 });
          const canvas = document.createElement("canvas");
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          canvas.className = "mb-2 w-full rounded border";
          canvas.setAttribute("aria-label", t("pageAria", { page: n }));
          canvas.setAttribute("role", "img");
          el?.appendChild(canvas);
          await page.render({ canvas, viewport }).promise;
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      el?.replaceChildren();
    };
  }, [documentId, t]);
  if (failed)
    return (
      <p className="text-muted-foreground text-sm">
        {t("pdfFailed")}{" "}
        <a className="underline" href={documentsApi.downloadUrl(documentId)}>
          {t("download")}
        </a>
      </p>
    );
  return <div ref={host} />;
}

export function EvidenceViewer({
  appId,
  activeCriterion,
  criterionTitles,
}: {
  appId: string;
  activeCriterion: string | null;
  criterionTitles: Record<string, string>;
}) {
  const t = useTranslations("screening.evidence");
  const { orgId } = useJobsContext();
  const [docIndex, setDocIndex] = useState(0);
  const [mode, setMode] = useState<"text" | "pdf">("text");
  const data = useQuery({
    queryKey: ["hr-applications", orgId ?? "", appId, "evidence-text"],
    queryFn: () =>
      api.get<EvidenceText>(`/hr/applications/${appId}/evidence-text/`, { orgId: orgId! }),
    enabled: !!orgId,
  });
  const doc = data.data?.documents[docIndex];
  const firstActive = useMemo(
    () => doc?.highlights.find((h) => activeCriterion && h.criteria.includes(activeCriterion)),
    [doc, activeCriterion],
  );
  useEffect(() => {
    if (!firstActive) return;
    document
      .getElementById(`evidence-${firstActive.claim_id}`)
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [firstActive]);

  return (
    <section aria-labelledby="evidence-viewer" className="min-w-0 rounded-lg border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="evidence-viewer" className="text-lg font-semibold">
          {t("title")}
        </h2>
        {doc?.original_available ? (
          <div role="group" aria-label={t("modeLabel")} className="flex gap-1">
            {(["text", "pdf"] as const).map((m) => (
              <Button
                key={m}
                size="sm"
                variant={mode === m ? "default" : "outline"}
                aria-pressed={mode === m}
                onClick={() => setMode(m)}
              >
                {t(`mode.${m}`)}
              </Button>
            ))}
          </div>
        ) : null}
      </div>
      <p className="text-muted-foreground mt-1 text-xs">{t("hint")}</p>
      {data.isPending ? (
        <PageSkeleton rows={3} />
      ) : data.isError ? (
        <ErrorState error={data.error} onRetry={() => data.refetch()} />
      ) : !doc ? (
        <p className="text-muted-foreground mt-2 text-sm">{t("none")}</p>
      ) : (
        <div className="mt-3 flex flex-col gap-3">
          {data.data.documents.length > 1 ? (
            <div role="group" aria-label={t("documents")} className="flex flex-wrap gap-1">
              {data.data.documents.map((d, i) => (
                <Button
                  key={d.document_id}
                  size="sm"
                  variant={i === docIndex ? "default" : "outline"}
                  aria-pressed={i === docIndex}
                  onClick={() => setDocIndex(i)}
                >
                  {d.filename}
                </Button>
              ))}
            </div>
          ) : null}
          {mode === "pdf" && doc.original_available ? (
            <PdfPages documentId={doc.document_id} />
          ) : (
            <div className="max-h-[70vh] overflow-auto overscroll-contain rounded border p-3">
              {doc.pages.map((page) => (
                <article key={page.number} aria-label={t("pageAria", { page: page.number })}>
                  <h3 className="text-muted-foreground mb-1 text-xs font-medium">
                    {t("page", { page: page.number })}
                  </h3>
                  <p className="mb-4 font-mono text-xs leading-5 break-words whitespace-pre-wrap">
                    {segments(
                      page.text,
                      doc.highlights.filter((h) => h.page === page.number),
                    ).map((seg, i) =>
                      seg.marks.length ? (
                        <mark
                          key={i}
                          id={`evidence-${seg.marks[0]!.claim_id}`}
                          title={seg.marks
                            .flatMap((m) => m.criteria)
                            .map((c) => criterionTitles[c] ?? "")
                            .filter(Boolean)
                            .join(", ")}
                          data-active={
                            activeCriterion
                              ? seg.marks.some((m) => m.criteria.includes(activeCriterion))
                              : undefined
                          }
                          className={
                            activeCriterion &&
                            seg.marks.some((m) => m.criteria.includes(activeCriterion))
                              ? "rounded bg-amber-300 px-0.5 ring-2 ring-amber-500 dark:bg-amber-700"
                              : "rounded bg-amber-100 px-0.5 dark:bg-amber-900"
                          }
                        >
                          {seg.text}
                        </mark>
                      ) : (
                        <Fragment key={i}>{seg.text}</Fragment>
                      ),
                    )}
                  </p>
                </article>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
