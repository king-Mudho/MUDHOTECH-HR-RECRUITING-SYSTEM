"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useId, useMemo, useState, type ReactNode, type UIEvent } from "react";

import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useJob, useJobsContext } from "@/features/jobs/hooks";
import { MAX_COMPARE } from "@/features/screening/compare";
import { BandBadge } from "@/features/screening/components";
import { rememberOrder } from "@/features/screening/review-workspace";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

import { APPLICATION_VIEWERS } from "./api";

type Row = components["schemas"]["HRApplicantRow"];
type SavedView = components["schemas"]["SavedView"];
type BulkResult = components["schemas"]["BulkActionResult"];
interface CursorPage {
  count: number;
  next_cursor: string | null;
  previous_cursor: string | null;
  results: Row[];
}

export interface ApplicantFilters {
  status?: string;
  band?: string;
  min_score?: string;
  max_score?: string;
  coverage_lt?: string;
  flags?: string;
  essentials?: string;
  tag?: string;
  assigned?: string;
  search?: string;
  ordering?: string;
}

const EDITORS = ["org_admin", "hr_manager", "recruiter"];
const ACTIVE = "submitted,processing,processing_error,under_review,needs_information,on_hold";
/** Built-in saved views (docs/08 §3.2). */
export const PRESETS: { key: string; params: ApplicantFilters }[] = [
  { key: "all_active", params: { status: ACTIVE } },
  { key: "needs_review", params: { status: "under_review", band: "review_needed" } },
  { key: "recommended", params: { status: "under_review", band: "recommended_for_review" } },
  { key: "eligibility", params: { band: "eligibility_review" } },
  { key: "errors", params: { status: "processing_error" } },
];
const BANDS = [
  "recommended_for_review",
  "review_needed",
  "eligibility_review",
  "lower_match",
  "manual_review_requested",
];
const ESSENTIALS = ["all_met", "unknown", "not_evidenced"];
const ORDERINGS = ["-score", "score", "-submitted_at", "submitted_at", "coverage"];
const ROW_HEIGHT = 64;
const WINDOW_AFTER = 200; // docs/08 §6: virtualise tables over 200 rows
const VIEWPORT_ROWS = 14;

function clean(f: ApplicantFilters): Record<string, string> {
  return Object.fromEntries(
    Object.entries(f).filter(([, v]) => v !== undefined && v !== ""),
  ) as Record<string, string>;
}

export function useApplicants(jobId: string, filters: ApplicantFilters) {
  const { orgId } = useJobsContext();
  return useInfiniteQuery({
    queryKey: ["hr-applications", orgId ?? "", "job", jobId, "applicants", clean(filters)],
    queryFn: ({ pageParam }) =>
      api.get<CursorPage>(`/hr/jobs/${jobId}/applications/`, {
        orgId: orgId!,
        query: { ...clean(filters), page_size: 100, ...(pageParam ? { cursor: pageParam } : {}) },
      }),
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !!orgId,
  });
}

function useSavedViews() {
  const { orgId } = useJobsContext();
  return useQuery({
    queryKey: ["hr-saved-views", orgId ?? ""],
    queryFn: () =>
      api.get<SavedView[]>("/hr/saved-views/", { orgId: orgId!, query: { scope: "applications" } }),
    enabled: !!orgId,
  });
}

/** Rows rendered inside a scroll container; only the visible window when the list is long. */
function useWindow(total: number) {
  const [top, setTop] = useState(0);
  const windowed = total > WINDOW_AFTER;
  const start = windowed ? Math.max(0, Math.floor(top / ROW_HEIGHT) - 5) : 0;
  const end = windowed ? Math.min(total, start + VIEWPORT_ROWS + 10) : total;
  return {
    windowed,
    start,
    end,
    onScroll: (e: UIEvent<HTMLDivElement>) => setTop(e.currentTarget.scrollTop),
    padTop: start * ROW_HEIGHT,
    padBottom: (total - end) * ROW_HEIGHT,
  };
}

function Essentials({ row }: { row: Row }) {
  const t = useTranslations("hrApplications.applicants");
  const e = row.essentials;
  if (!e) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className="whitespace-nowrap"
      aria-label={t("essentialsAria", {
        met: e.met,
        unknown: e.unknown,
        notEvidenced: e.not_evidenced,
      })}
    >
      ✓ {e.met} · ? {e.unknown} · ✗ {e.not_evidenced}
    </span>
  );
}

function Filters({
  value,
  onChange,
}: {
  value: ApplicantFilters;
  onChange: (next: ApplicantFilters) => void;
}) {
  const t = useTranslations("hrApplications.applicants");
  const tb = useTranslations("screening.bands");
  const id = useId();
  const set = (patch: ApplicantFilters) => onChange({ ...value, ...patch });
  const select = (key: keyof ApplicantFilters, label: string, options: [string, string][]) => (
    <div className="flex flex-col gap-1">
      <Label htmlFor={`${id}-${key}`}>{label}</Label>
      <select
        id={`${id}-${key}`}
        className="border-input h-9 rounded-md border bg-transparent px-2 text-sm"
        value={value[key] ?? ""}
        onChange={(e) => set({ [key]: e.target.value || undefined })}
      >
        <option value="">{t("any")}</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </div>
  );
  return (
    <fieldset className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <legend className="sr-only">{t("filtersLegend")}</legend>
      {select(
        "band",
        t("band"),
        BANDS.map((b) => [b, tb(b)]),
      )}
      {select(
        "essentials",
        t("essentials"),
        ESSENTIALS.map((e) => [e, t(`essentialsState.${e}`)]),
      )}
      {select("assigned", t("assigned"), [
        ["me", t("assignedMe")],
        ["none", t("assignedNone")],
      ])}
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${id}-min`}>{t("minScore")}</Label>
        <Input
          id={`${id}-min`}
          type="number"
          min={0}
          max={100}
          inputMode="numeric"
          value={value.min_score ?? ""}
          onChange={(e) => set({ min_score: e.target.value || undefined })}
          className="h-9"
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${id}-tag`}>{t("tag")}</Label>
        <Input
          id={`${id}-tag`}
          value={value.tag ?? ""}
          onChange={(e) => set({ tag: e.target.value.trim() || undefined })}
          className="h-9"
        />
      </div>
      <label className="flex items-center gap-2 self-end pb-2 text-sm">
        <input
          type="checkbox"
          className="size-4"
          checked={value.coverage_lt === "0.6"}
          onChange={(e) => set({ coverage_lt: e.target.checked ? "0.6" : undefined })}
        />
        {t("lowCoverage")}
      </label>
    </fieldset>
  );
}

function BulkBar({
  jobId,
  selected,
  onDone,
}: {
  jobId: string;
  selected: string[];
  onDone: (message: string) => void;
}) {
  const t = useTranslations("hrApplications.applicants.bulk");
  const { orgId, role } = useJobsContext();
  const client = useQueryClient();
  const [mode, setMode] = useState<"" | "tag" | "clarification">("");
  const [text, setText] = useState("");
  const inputId = useId();
  const run = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<BulkResult>(
        `/hr/jobs/${jobId}/applications/bulk/`,
        { ...body, application_ids: selected },
        { orgId: orgId! },
      ),
    onSuccess: (res) => {
      setMode("");
      setText("");
      void client.invalidateQueries({ queryKey: ["hr-applications", orgId ?? "", "job", jobId] });
      onDone(t("done", { done: res.done, skipped: res.skipped.length }));
    },
  });
  if (!selected.length || !EDITORS.includes(role ?? "")) return null;
  const error = run.error instanceof ApiError ? run.error.message : run.error ? t("failed") : null;
  return (
    <section
      aria-label={t("label")}
      className="bg-muted/40 flex flex-col gap-2 rounded-lg border p-3 text-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{t("selected", { count: selected.length })}</span>
        <Button size="sm" variant="outline" onClick={() => run.mutate({ action: "assign_me" })}>
          {t("assignMe")}
        </Button>
        <Button size="sm" variant="outline" onClick={() => setMode("tag")}>
          {t("tag")}
        </Button>
        <Button size="sm" variant="outline" onClick={() => setMode("clarification")}>
          {t("clarification")}
        </Button>
        <Button size="sm" onClick={() => run.mutate({ action: "propose_shortlist" })}>
          {t("propose")}
        </Button>
        {selected.length >= 2 && selected.length <= MAX_COMPARE ? (
          <Button asChild size="sm" variant="outline">
            <Link href={`/hr/compare?ids=${selected.join(",")}`}>{t("compare")}</Link>
          </Button>
        ) : null}
      </div>
      {mode ? (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (mode === "tag") run.mutate({ action: "tag", tags: [text] });
            else run.mutate({ action: "clarification", questions: [{ prompt: text }] });
          }}
        >
          <div className="flex min-w-60 flex-1 flex-col gap-1">
            <Label htmlFor={inputId}>{mode === "tag" ? t("tagLabel") : t("questionLabel")}</Label>
            <Input id={inputId} value={text} onChange={(e) => setText(e.target.value)} />
          </div>
          <Button type="submit" size="sm" disabled={run.isPending || !text.trim()}>
            {t("apply")}
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => setMode("")}>
            {t("cancel")}
          </Button>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function SavedViews({
  current,
  onPick,
}: {
  current: ApplicantFilters;
  onPick: (f: ApplicantFilters) => void;
}) {
  const t = useTranslations("hrApplications.applicants");
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const views = useSavedViews();
  const [name, setName] = useState("");
  const nameId = useId();
  const save = useMutation({
    mutationFn: () =>
      api.post<SavedView>(
        "/hr/saved-views/",
        { name, scope: "applications", params: clean(current) },
        { orgId: orgId! },
      ),
    onSuccess: () => {
      setName("");
      void client.invalidateQueries({ queryKey: ["hr-saved-views", orgId ?? ""] });
    },
  });
  const same = (p: ApplicantFilters) =>
    JSON.stringify(clean(p)) === JSON.stringify(clean({ ...current, search: undefined }));
  const chip = (key: string, label: ReactNode, params: ApplicantFilters) => (
    <Button
      key={key}
      size="sm"
      variant={same(params) ? "default" : "outline"}
      aria-pressed={same(params)}
      onClick={() => onPick(params)}
    >
      {label}
    </Button>
  );
  return (
    <div className="flex flex-col gap-2">
      <div role="group" aria-label={t("views")} className="flex flex-wrap gap-1.5">
        {PRESETS.map((p) => chip(p.key, t(`presets.${p.key}`), p.params))}
        {(views.data ?? []).map((v) => chip(v.id, v.name, v.params as unknown as ApplicantFilters))}
      </div>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor={nameId}>{t("saveViewLabel")}</Label>
          <Input
            id={nameId}
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-9 w-56"
          />
        </div>
        <Button type="submit" size="sm" variant="outline" disabled={save.isPending || !name.trim()}>
          {t("saveView")}
        </Button>
      </form>
    </div>
  );
}

export function ApplicantsTable({ jobId }: { jobId: string }) {
  const t = useTranslations("hrApplications");
  const ta = useTranslations("hrApplications.applicants");
  const format = useFormatter();
  const { role, isPending, orgId } = useJobsContext();
  const job = useJob(jobId);
  const [filters, setFilters] = useState<ApplicantFilters>({
    status: ACTIVE,
    ordering: "-score",
  });
  const [searchInput, setSearchInput] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [announce, setAnnounce] = useState("");
  useEffect(() => {
    const id = setTimeout(
      () => setFilters((f) => ({ ...f, search: searchInput.trim() || undefined })),
      300,
    );
    return () => clearTimeout(id);
  }, [searchInput]);
  const query = useApplicants(jobId, filters);
  const rows = useMemo(
    () =>
      (query.data as InfiniteData<CursorPage> | undefined)?.pages.flatMap((p) => p.results) ?? [],
    [query.data],
  );
  const count = (query.data as InfiniteData<CursorPage> | undefined)?.pages[0]?.count ?? 0;
  useEffect(() => {
    if (rows.length)
      rememberOrder(
        jobId,
        rows.map((r) => r.id),
      );
  }, [jobId, rows]);
  const win = useWindow(rows.length);

  if (isPending) return <PageSkeleton />;
  if (!orgId || !role || !APPLICATION_VIEWERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  const canBulk = EDITORS.includes(role);
  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const allShown = rows.length > 0 && rows.every((r) => selected.includes(r.id));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <Link
          href={`/hr/jobs/${jobId}`}
          className="text-muted-foreground text-sm underline-offset-2 hover:underline"
        >
          {t("backToJob")}
        </Link>
        <h1 className="text-2xl font-semibold">
          {t("title")}
          {job.data ? (
            <span className="text-muted-foreground font-normal"> · {job.data.title}</span>
          ) : null}
        </h1>
        <p className="text-muted-foreground text-sm">
          {t("phaseNote")}{" "}
          <Link href={`/hr/jobs/${jobId}/pipeline`} className="underline">
            {t("openPipeline")}
          </Link>{" "}
          ·{" "}
          <Link href={`/hr/jobs/${jobId}/screening`} className="underline">
            {t("openScreening")}
          </Link>{" "}
          ·{" "}
          <Link href={`/hr/jobs/${jobId}/shortlist`} className="underline">
            {ta("openShortlist")}
          </Link>
        </p>
      </div>

      <SavedViews
        current={filters}
        onPick={(f) => {
          setFilters({ ordering: filters.ordering, ...f });
          setSelected([]);
        }}
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex flex-col gap-1.5 sm:w-72">
          <Label htmlFor="application-search">{t("search")}</Label>
          <div className="relative">
            <Search
              aria-hidden="true"
              className="text-muted-foreground absolute top-3 left-2.5 size-4"
            />
            <Input
              id="application-search"
              type="search"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder={t("searchPlaceholder")}
              className="h-10 pl-8"
            />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="applicant-ordering">{ta("sort")}</Label>
          <select
            id="applicant-ordering"
            className="border-input h-10 rounded-md border bg-transparent px-2 text-sm"
            value={filters.ordering ?? "-score"}
            onChange={(e) => setFilters({ ...filters, ordering: e.target.value })}
          >
            {ORDERINGS.map((o) => (
              <option key={o} value={o}>
                {ta(`orderings.${o}`)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <Filters value={filters} onChange={setFilters} />
      <p className="text-muted-foreground text-xs">{ta("aiNotice")}</p>

      {canBulk ? (
        <BulkBar
          jobId={jobId}
          selected={selected}
          onDone={(m) => {
            setSelected([]);
            setAnnounce(m);
          }}
        />
      ) : null}
      <p role="status" aria-live="polite" className="sr-only">
        {announce}
      </p>

      {query.isPending ? (
        <PageSkeleton />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState title={t("noMatchesTitle")} description={t("noMatches")} />
      ) : (
        <>
          <div
            onScroll={win.onScroll}
            className="overflow-auto rounded-lg border"
            style={win.windowed ? { maxHeight: ROW_HEIGHT * VIEWPORT_ROWS } : undefined}
            data-windowed={win.windowed}
          >
            <table className="w-full text-sm" aria-rowcount={count + 1}>
              <caption className="sr-only">{t("caption")}</caption>
              <thead className="bg-muted/50 sticky top-0 text-left">
                <tr>
                  {canBulk ? (
                    <th scope="col" className="w-10 px-3 py-2">
                      <input
                        type="checkbox"
                        className="size-4"
                        aria-label={ta("selectAll")}
                        checked={allShown}
                        onChange={() => setSelected(allShown ? [] : rows.map((r) => r.id))}
                      />
                    </th>
                  ) : null}
                  {(
                    [
                      "candidate",
                      "band",
                      "score",
                      "essentials",
                      "flags",
                      "status",
                      "submitted",
                      "assigned",
                    ] as const
                  ).map((c) => (
                    <th key={c} scope="col" className="px-3 py-2 font-medium">
                      {ta(`columns.${c}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {win.padTop ? <tr aria-hidden="true" style={{ height: win.padTop }} /> : null}
                {rows.slice(win.start, win.end).map((a, i) => (
                  <tr
                    key={a.id}
                    className="border-t"
                    style={{ height: ROW_HEIGHT }}
                    aria-rowindex={win.start + i + 2}
                  >
                    {canBulk ? (
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          className="size-4"
                          aria-label={ta("select", { name: a.candidate_name || t("unnamed") })}
                          checked={selected.includes(a.id)}
                          onChange={() => toggle(a.id)}
                        />
                      </td>
                    ) : null}
                    <td className="px-3 py-2">
                      <Link
                        href={`/hr/applications/${a.id}`}
                        className="font-medium underline-offset-2 hover:underline"
                      >
                        {a.candidate_name || t("unnamed")}
                      </Link>
                      <div className="text-muted-foreground font-mono text-xs">{a.reference}</div>
                    </td>
                    <td className="px-3 py-2">
                      {a.ai_band ? <BandBadge band={a.ai_band} /> : "—"}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {a.score === null ? "—" : Math.round(a.score)}
                      {a.coverage !== null ? (
                        <span className="text-muted-foreground text-xs">
                          {" "}
                          · {ta("coverageShort", { value: Math.round(a.coverage * 100) })}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <Essentials row={a} />
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {a.flags.map((f) => (
                          <Badge key={f} variant="outline">
                            {ta.has(`flags.${f}`) ? ta(`flags.${f}`) : f}
                          </Badge>
                        ))}
                        {a.objects_to_automated_processing ? (
                          <Badge variant="outline">{t("humanOnly")}</Badge>
                        ) : null}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={a.status} />
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {a.submitted_at
                        ? format.dateTime(new Date(a.submitted_at), { dateStyle: "medium" })
                        : "—"}
                    </td>
                    <td className="px-3 py-2">{a.assigned_name || "—"}</td>
                  </tr>
                ))}
                {win.padBottom ? <tr aria-hidden="true" style={{ height: win.padBottom }} /> : null}
              </tbody>
            </table>
          </div>
          <nav
            aria-label={t("pagination")}
            className="flex items-center justify-between gap-2 text-sm"
          >
            <span aria-live="polite">{ta("shown", { shown: rows.length, count })}</span>
            {query.hasNextPage ? (
              <Button
                variant="outline"
                size="sm"
                disabled={query.isFetchingNextPage}
                onClick={() => void query.fetchNextPage()}
              >
                {query.isFetchingNextPage ? ta("loading") : ta("loadMore")}
              </Button>
            ) : null}
          </nav>
        </>
      )}
    </div>
  );
}
