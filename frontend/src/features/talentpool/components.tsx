"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState, type FormEvent } from "react";

import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useJobs, useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

export type TalentCandidate = components["schemas"]["TalentCandidate"];
type Page = components["schemas"]["PaginatedTalentCandidateList"];

export const TALENT_SEARCHERS = ["org_admin", "hr_manager", "recruiter"];

export interface TalentFilters {
  q: string;
  skill: string;
  tag: string;
}

/** Query string for the search endpoint: one ``skill`` param per comma-separated skill. */
export function talentQuery(f: TalentFilters): Record<string, string | string[] | undefined> {
  const skills = f.skill
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return {
    q: f.q.trim() || undefined,
    skill: skills.length ? skills : undefined,
    tag: f.tag.trim() || undefined,
    page_size: "25",
  };
}

/** Tags typed as "a, b, c": trimmed, de-duplicated, at most 10. */
export function parseTags(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(",")) {
    const tag = raw.split(/\s+/).filter(Boolean).join(" ");
    if (tag && !out.includes(tag)) out.push(tag);
  }
  return out.slice(0, 10);
}

const key = (orgId: string, f: TalentFilters) => ["talent-pool", orgId, f] as const;

export function TalentPoolRoute() {
  const t = useTranslations("talentPool");
  const { orgId, role, isPending } = useJobsContext();
  const [draft, setDraft] = useState<TalentFilters>({ q: "", skill: "", tag: "" });
  const [filters, setFilters] = useState<TalentFilters>(draft);
  const ids = { q: useId(), skill: useId(), tag: useId() };
  const results = useQuery({
    queryKey: key(orgId ?? "", filters),
    queryFn: () =>
      api.get<Page>("/hr/talent-pool/", {
        orgId: orgId!,
        query: talentQuery(filters),
      }),
    enabled: !!orgId && !!role && TALENT_SEARCHERS.includes(role),
  });
  if (isPending) return <PageSkeleton />;
  if (!role || !TALENT_SEARCHERS.includes(role))
    return <ForbiddenState description={t("forbidden")} />;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setFilters(draft);
  };
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-muted-foreground text-sm">{t("intro")}</p>
      </div>
      <form
        role="search"
        aria-label={t("searchLabel")}
        onSubmit={submit}
        className="grid gap-3 rounded-lg border p-3 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end"
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={ids.q}>{t("q")}</Label>
          <Input
            id={ids.q}
            className="h-10"
            value={draft.q}
            placeholder={t("qPlaceholder")}
            onChange={(e) => setDraft({ ...draft, q: e.target.value })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={ids.skill}>{t("skills")}</Label>
          <Input
            id={ids.skill}
            className="h-10"
            value={draft.skill}
            placeholder={t("skillsPlaceholder")}
            onChange={(e) => setDraft({ ...draft, skill: e.target.value })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={ids.tag}>{t("tag")}</Label>
          <Input
            id={ids.tag}
            className="h-10"
            value={draft.tag}
            onChange={(e) => setDraft({ ...draft, tag: e.target.value })}
          />
        </div>
        <Button type="submit" className="h-10">
          {t("search")}
        </Button>
      </form>
      {results.isPending ? (
        <PageSkeleton />
      ) : results.isError ? (
        <ErrorState error={results.error} onRetry={() => results.refetch()} />
      ) : results.data.results.length === 0 ? (
        <EmptyState title={t("emptyTitle")} description={t("empty")} />
      ) : (
        <>
          <p className="text-muted-foreground text-sm" aria-live="polite">
            {t("count", { count: results.data.count })}
          </p>
          <ul className="flex flex-col gap-3">
            {results.data.results.map((c) => (
              <TalentCard key={c.id} candidate={c} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function TalentCard({ candidate: c }: { candidate: TalentCandidate }) {
  const t = useTranslations("talentPool");
  const format = useFormatter();
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [tagText, setTagText] = useState(c.tags.join(", "));
  const [jobId, setJobId] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const ids = { tags: useId(), job: useId() };
  const jobs = useJobs({ status: "published" });
  const refresh = () => client.invalidateQueries({ queryKey: ["talent-pool", orgId ?? ""] });
  const fail = (err: unknown) =>
    setMessage({ ok: false, text: err instanceof ApiError ? err.message : t("failed") });
  const saveTags = useMutation({
    mutationFn: () =>
      api.patch<TalentCandidate>(
        `/hr/talent-pool/${c.id}/`,
        { tags: parseTags(tagText) },
        { orgId: orgId! },
      ),
    onSuccess: async () => {
      setEditing(false);
      setMessage(null);
      await refresh();
    },
    onError: fail,
  });
  const invite = useMutation({
    mutationFn: () =>
      api.post(`/hr/talent-pool/${c.id}/invite/`, { job_id: jobId }, { orgId: orgId! }),
    onSuccess: async () => {
      setMessage({ ok: true, text: t("invited") });
      setJobId("");
      await refresh();
    },
    onError: fail,
  });
  const openJobs = (jobs.data?.results ?? []).filter((j) => !c.invited_job_ids.includes(j.id));
  return (
    <li className="flex flex-col gap-2 rounded-lg border p-3 text-sm">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="text-base font-semibold">{c.name || t("unnamed")}</h2>
        {c.headline ? <span className="text-muted-foreground">{c.headline}</span> : null}
        {c.city ? <span className="text-muted-foreground">· {c.city}</span> : null}
      </div>
      {c.latest_title ? <p>{t("latestTitle", { title: c.latest_title })}</p> : null}
      {c.qualifications.length ? <p>{c.qualifications.join(" · ")}</p> : null}
      {c.skills.length ? (
        <ul aria-label={t("skillsOf", { name: c.name })} className="flex flex-wrap gap-1">
          {c.skills.map((s) => (
            <li key={s}>
              <Badge variant="secondary">{s}</Badge>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-muted-foreground text-xs">
        {t("consentUntil", {
          date: format.dateTime(new Date(c.expires_at), { dateStyle: "medium" }),
        })}
        {c.latest_application ? (
          <>
            {" · "}
            <Link className="underline" href={`/hr/applications/${c.latest_application.id}`}>
              {t("lastApplication", {
                reference: c.latest_application.reference ?? "",
                job: c.latest_application.job_title,
              })}
            </Link>
          </>
        ) : null}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {c.tags.map((tag) => (
          <Badge key={tag} variant="outline">
            {tag}
          </Badge>
        ))}
        {!editing ? (
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
            {t("editTags")}
          </Button>
        ) : (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              saveTags.mutate();
            }}
          >
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.tags}>{t("tagsLabel")}</Label>
              <Input
                id={ids.tags}
                className="h-9"
                value={tagText}
                onChange={(e) => setTagText(e.target.value)}
              />
            </div>
            <Button size="sm" type="submit" disabled={saveTags.isPending}>
              {t("saveTags")}
            </Button>
          </form>
        )}
      </div>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (jobId) invite.mutate();
        }}
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor={ids.job}>{t("inviteTo")}</Label>
          <select
            id={ids.job}
            className="border-input bg-background h-9 rounded-md border px-2"
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
          >
            <option value="">{t("chooseVacancy")}</option>
            {openJobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.title}
              </option>
            ))}
          </select>
        </div>
        <Button size="sm" type="submit" disabled={!jobId || invite.isPending}>
          {t("invite")}
        </Button>
      </form>
      <p
        aria-live="polite"
        className={message?.ok ? "text-sm text-green-700" : "text-destructive text-sm"}
      >
        {message?.text}
      </p>
    </li>
  );
}
