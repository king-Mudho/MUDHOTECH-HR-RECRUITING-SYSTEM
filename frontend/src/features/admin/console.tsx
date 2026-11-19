"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState, type FormEvent, type ReactNode } from "react";

import { EmptyState, ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMe } from "@/features/auth/session";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

type S = components["schemas"];
type Overview = S["PlatformOverview"];
type OrgDetail = S["PlatformOrgDetail"];
type PlatformUser = S["PlatformUser"];
type Flag = S["PlatformFlag"];
type DeadLetter = S["DeadLetter"];
type System = S["System"];
type TaxonomyStatus = S["TaxonomyStatus"];
type Skill = S["CuratedSkill"];
type Level = S["CuratedQualificationLevel"];

function useIsPlatformAdmin() {
  const { data } = useMe();
  return data?.platform_role === "platform_admin";
}

function errorText(err: unknown, fallback: string): string | null {
  if (!err) return null;
  return err instanceof ApiError ? err.message : fallback;
}

function Page({ title, intro, children }: { title: string; intro?: string; children: ReactNode }) {
  return (
    <main id="main-content" className="flex flex-col gap-6 p-4 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {intro ? <p className="text-muted-foreground text-sm">{intro}</p> : null}
      </div>
      {children}
    </main>
  );
}

function Tile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-md border p-3">
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
    </div>
  );
}

/** Metric rows from the health collectors: [{metric, value, unit, dimensions}] or {error}. */
export function healthRows(health: Record<string, unknown>): { name: string; value: string }[] {
  const rows: { name: string; value: string }[] = [];
  for (const [name, entry] of Object.entries(health)) {
    if (Array.isArray(entry)) {
      for (const m of entry as { metric: string; value: number; dimensions?: object }[]) {
        const dims = Object.values(m.dimensions ?? {}).join(" ");
        rows.push({ name: dims ? `${m.metric} (${dims})` : m.metric, value: String(m.value) });
      }
    } else if (entry && typeof entry === "object" && "error" in entry) {
      rows.push({ name, value: `unavailable: ${String((entry as { error: string }).error)}` });
    }
  }
  return rows;
}

function HealthTable({ health, caption }: { health: Record<string, unknown>; caption: string }) {
  const rows = healthRows(health);
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">{caption}</caption>
      <tbody>
        {rows.map((r) => (
          <tr key={r.name} className="border-t">
            <th scope="row" className="py-1 pr-2 text-left font-normal">
              {r.name}
            </th>
            <td className="py-1 text-right tabular-nums">{r.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// --- dashboard ----------------------------------------------------------------------------------
export function AdminDashboard() {
  const t = useTranslations("admin.console");
  const q = useQuery({
    queryKey: ["admin", "overview"],
    queryFn: () => api.get<Overview>("/platform/overview/"),
  });
  return (
    <Page title={t("dashboard.title")} intro={t("dashboard.intro")}>
      {q.isPending ? (
        <PageSkeleton />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Tile
              label={t("dashboard.tenants")}
              value={Object.values(q.data.tenants).reduce((a, b) => a + b, 0)}
            />
            <Tile label={t("dashboard.activeVacancies")} value={q.data.active_vacancies} />
            <Tile label={t("dashboard.deadLetters")} value={q.data.error_rates.dead_letters_open} />
            <Tile
              label={t("dashboard.parseFailures")}
              value={
                q.data.error_rates.extraction_failure_rate_24h === null
                  ? "—"
                  : `${Math.round(q.data.error_rates.extraction_failure_rate_24h * 1000) / 10}%`
              }
            />
          </div>
          <section aria-labelledby="tenants" className="rounded-lg border p-4">
            <h2 id="tenants" className="text-lg font-semibold">
              {t("dashboard.byStatus")}
            </h2>
            <ul className="mt-2 flex flex-wrap gap-2 text-sm">
              {Object.entries(q.data.tenants).map(([status, n]) => (
                <li key={status}>
                  <Badge variant="outline">
                    {status.replaceAll("_", " ")}: {n}
                  </Badge>
                </li>
              ))}
            </ul>
          </section>
          <section aria-labelledby="per-day" className="rounded-lg border p-4">
            <h2 id="per-day" className="text-lg font-semibold">
              {t("dashboard.perDay")}
            </h2>
            <table className="mt-2 w-full text-sm">
              <caption className="sr-only">{t("dashboard.perDay")}</caption>
              <tbody>
                {q.data.applications_per_day.map((d) => {
                  const max = Math.max(1, ...q.data.applications_per_day.map((x) => x.count));
                  return (
                    <tr key={d.day} className="border-t">
                      <th scope="row" className="w-28 py-1 text-left font-normal">
                        {d.day}
                      </th>
                      <td className="py-1">
                        <div className="flex items-center gap-2">
                          <div
                            className="bg-primary h-3 rounded-r"
                            style={{
                              width: `${(d.count / max) * 100}%`,
                              minWidth: d.count ? 4 : 0,
                            }}
                            aria-hidden="true"
                          />
                          <span className="tabular-nums">{d.count}</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
          <section aria-labelledby="queues" className="rounded-lg border p-4">
            <h2 id="queues" className="text-lg font-semibold">
              {t("dashboard.queues")}
            </h2>
            <HealthTable health={q.data.health} caption={t("dashboard.queues")} />
          </section>
        </>
      )}
    </Page>
  );
}

// --- organisation detail ------------------------------------------------------------------------
export function AdminOrganisationDetailRoute() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("admin.console.org");
  const q = useQuery({
    queryKey: ["admin", "organisation", id],
    queryFn: () => api.get<OrgDetail>(`/platform/organisations/${id}/detail/`),
  });
  return (
    <Page title={q.data?.name ?? t("title")}>
      <Link href="/admin/organisations" className="text-sm underline">
        {t("back")}
      </Link>
      {q.isPending ? (
        <PageSkeleton />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <p className="text-sm">
            {t("status", { status: q.data.status.replaceAll("_", " ") })} ·{" "}
            {q.data.verified_at ? t("verified") : t("unverified")}
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label={t("vacancies")} value={q.data.usage.active_vacancies} />
            <Tile label={t("applications")} value={q.data.usage.applications_this_month} />
            <Tile label={t("evaluations")} value={q.data.usage.ai_evaluations_this_month} />
            <Tile
              label={t("storage")}
              value={`${Math.round((q.data.usage.storage_bytes / 1024 / 1024) * 10) / 10} MB`}
            />
          </div>
          <section aria-labelledby="members" className="rounded-lg border p-4">
            <h2 id="members" className="text-lg font-semibold">
              {t("members")}
            </h2>
            <ul className="mt-2 flex flex-wrap gap-2 text-sm">
              {Object.entries(q.data.members_by_role).map(([role, n]) => (
                <li key={role}>
                  <Badge variant="outline">
                    {role.replaceAll("_", " ")}: {n}
                  </Badge>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </Page>
  );
}

// --- users --------------------------------------------------------------------------------------
export function AdminUsers() {
  const t = useTranslations("admin.console.users");
  const format = useFormatter();
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const id = useId();
  const rows = useQuery({
    queryKey: ["admin", "users", q],
    queryFn: () => api.get<PlatformUser[]>("/platform/users/", { query: { q } }),
    enabled: q.length >= 3,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setQ(draft.trim());
  };
  return (
    <Page title={t("title")} intro={t("intro")}>
      <form role="search" onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={id}>{t("search")}</Label>
          <Input
            id={id}
            className="h-10 w-72"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        </div>
        <Button type="submit" className="h-10">
          {t("go")}
        </Button>
      </form>
      {q.length < 3 ? (
        <p className="text-muted-foreground text-sm">{t("hint")}</p>
      ) : rows.isPending ? (
        <PageSkeleton rows={2} />
      ) : rows.isError ? (
        <ErrorState error={rows.error} onRetry={() => rows.refetch()} />
      ) : rows.data.length === 0 ? (
        <EmptyState title={t("none")} description={t("hint")} />
      ) : (
        <table className="w-full text-sm">
          <caption className="sr-only">{t("title")}</caption>
          <thead>
            <tr className="text-muted-foreground text-left text-xs">
              <th scope="col">{t("email")}</th>
              <th scope="col">{t("name")}</th>
              <th scope="col">{t("role")}</th>
              <th scope="col">{t("memberships")}</th>
              <th scope="col">{t("lastLogin")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.data.map((u) => (
              <tr key={u.id} className="border-t">
                <td className="py-1">{u.email}</td>
                <td>{u.name}</td>
                <td>{u.platform_role === "none" ? "—" : u.platform_role.replaceAll("_", " ")}</td>
                <td className="tabular-nums">{u.memberships}</td>
                <td>
                  {u.last_login
                    ? format.dateTime(new Date(u.last_login), { dateStyle: "medium" })
                    : "—"}
                  {u.is_active ? "" : ` · ${t("inactive")}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Page>
  );
}

// --- feature flags ------------------------------------------------------------------------------
export function AdminFlags() {
  const t = useTranslations("admin.console.flags");
  const isAdmin = useIsPlatformAdmin();
  const client = useQueryClient();
  const [key, setKey] = useState("");
  const [org, setOrg] = useState("");
  const ids = { key: useId(), org: useId() };
  const flags = useQuery({
    queryKey: ["admin", "flags"],
    queryFn: () => api.get<Flag[]>("/platform/flags/"),
  });
  const set = useMutation({
    mutationFn: (body: { key: string; enabled: boolean; organisation_id?: string | null }) =>
      api.post<Flag[]>("/platform/flags/", body),
    onSuccess: (data) => client.setQueryData(["admin", "flags"], data),
  });
  return (
    <Page title={t("title")} intro={t("intro")}>
      {flags.isPending ? (
        <PageSkeleton />
      ) : flags.isError ? (
        <ErrorState error={flags.error} onRetry={() => flags.refetch()} />
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {flags.data.map((f) => (
            <li key={f.key} className="flex flex-col gap-1 rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <code className="font-medium">{f.key}</code>
                <Badge variant="outline">
                  {f.global === null ? t("default") : f.global ? t("on") : t("off")}
                </Badge>
                {isAdmin ? (
                  <span className="ml-auto flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={set.isPending}
                      onClick={() => set.mutate({ key: f.key, enabled: true })}
                    >
                      {t("turnOn")}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={set.isPending}
                      onClick={() => set.mutate({ key: f.key, enabled: false })}
                    >
                      {t("turnOff")}
                    </Button>
                  </span>
                ) : null}
              </div>
              {f.description ? <p className="text-muted-foreground">{f.description}</p> : null}
              {f.overrides.length ? (
                <ul className="text-muted-foreground text-xs">
                  {f.overrides.map((o) => (
                    <li key={o.organisation_id}>
                      {o.organisation_name || o.organisation_id}: {o.enabled ? t("on") : t("off")}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {isAdmin ? (
        <form
          className="flex flex-wrap items-end gap-2 rounded-md border p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (key) set.mutate({ key, enabled: true, organisation_id: org || null });
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={ids.key}>{t("key")}</Label>
            <Input
              id={ids.key}
              className="h-10"
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={ids.org}>{t("organisation")}</Label>
            <Input
              id={ids.org}
              className="h-10 w-80"
              value={org}
              onChange={(e) => setOrg(e.target.value)}
            />
          </div>
          <Button type="submit" className="h-10" disabled={!key || set.isPending}>
            {t("enable")}
          </Button>
        </form>
      ) : null}
      <p aria-live="polite" className="text-destructive text-sm">
        {errorText(set.error, t("failed"))}
      </p>
    </Page>
  );
}

// --- dead letters -------------------------------------------------------------------------------
export function AdminDeadLetters() {
  const t = useTranslations("admin.console.deadLetters");
  const format = useFormatter();
  const isAdmin = useIsPlatformAdmin();
  const client = useQueryClient();
  const [all, setAll] = useState(false);
  const rows = useQuery({
    queryKey: ["admin", "dead-letters", all],
    queryFn: () =>
      api.get<DeadLetter[]>("/platform/dead-letters/", {
        query: { all: all ? "true" : undefined },
      }),
  });
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "dead-letters"] });
  const retry = useMutation({
    mutationFn: (id: string) => api.post<DeadLetter>(`/platform/dead-letters/${id}/retry/`),
    onSuccess: refresh,
  });
  const resolve = useMutation({
    mutationFn: (id: string) =>
      api.post<DeadLetter>(`/platform/dead-letters/${id}/resolve/`, {
        reason: "Resolved by platform admin",
      }),
    onSuccess: refresh,
  });
  return (
    <Page title={t("title")} intro={t("intro")}>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-5"
          checked={all}
          onChange={(e) => setAll(e.target.checked)}
        />
        {t("showResolved")}
      </label>
      {rows.isPending ? (
        <PageSkeleton />
      ) : rows.isError ? (
        <ErrorState error={rows.error} onRetry={() => rows.refetch()} />
      ) : rows.data.length === 0 ? (
        <EmptyState title={t("none")} description={t("noneBody")} />
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {rows.data.map((d) => (
            <li key={d.id} className="flex flex-col gap-1 rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <code className="font-medium">{d.task_name}</code>
                <span className="text-muted-foreground">
                  {format.dateTime(new Date(d.created_at), {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </span>
                {d.resolved_at ? <Badge variant="outline">{t("resolved")}</Badge> : null}
                {isAdmin && !d.resolved_at ? (
                  <span className="ml-auto flex gap-2">
                    <Button size="sm" disabled={retry.isPending} onClick={() => retry.mutate(d.id)}>
                      {t("retry")}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={resolve.isPending}
                      onClick={() => resolve.mutate(d.id)}
                    >
                      {t("resolve")}
                    </Button>
                  </span>
                ) : null}
              </div>
              <p className="text-muted-foreground font-mono text-xs break-all">
                {d.error.slice(0, 300)}
              </p>
              {d.request_id ? (
                <p className="text-muted-foreground text-xs">
                  {t("request", { id: d.request_id })}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Page>
  );
}

// --- system health ------------------------------------------------------------------------------
export function AdminSystem() {
  const t = useTranslations("admin.console.system");
  const q = useQuery({
    queryKey: ["admin", "system"],
    queryFn: () => api.get<System>("/platform/system/"),
    refetchInterval: 30_000,
  });
  return (
    <Page title={t("title")} intro={t("intro")}>
      {q.isPending ? (
        <PageSkeleton />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <>
          <section aria-labelledby="checks" className="rounded-lg border p-4">
            <h2 id="checks" className="text-lg font-semibold">
              {t("checks")}
            </h2>
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {Object.entries(
                q.data.checks as Record<string, { status: string; error?: string }>,
              ).map(([name, c]) => (
                <li key={name} className="flex items-center gap-2">
                  <span className="w-28">{name}</span>
                  <Badge variant={c.status === "ok" ? "outline" : "destructive"}>
                    {c.status === "ok" ? t("ok") : `${t("error")}${c.error ? `: ${c.error}` : ""}`}
                  </Badge>
                </li>
              ))}
            </ul>
          </section>
          <section aria-labelledby="queues" className="rounded-lg border p-4">
            <h2 id="queues" className="text-lg font-semibold">
              {t("queues")}
            </h2>
            <HealthTable health={q.data.health} caption={t("queues")} />
          </section>
        </>
      )}
    </Page>
  );
}

// --- taxonomy -----------------------------------------------------------------------------------
const CATEGORIES = [
  "software_it",
  "finance",
  "engineering",
  "health",
  "sales_marketing",
  "logistics",
  "education",
  "agriculture",
  "mining",
  "ngo",
  "business",
  "legal",
  "language",
  "general",
];

export function AdminTaxonomy() {
  const t = useTranslations("admin.console.taxonomy");
  const format = useFormatter();
  const isAdmin = useIsPlatformAdmin();
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("software_it");
  const [notes, setNotes] = useState("");
  const ids = { q: useId(), name: useId(), cat: useId(), notes: useId() };
  const status = useQuery({
    queryKey: ["admin", "taxonomy"],
    queryFn: () => api.get<TaxonomyStatus>("/platform/taxonomy/"),
  });
  const skills = useQuery({
    queryKey: ["admin", "taxonomy", "skills", q],
    queryFn: () => api.get<Skill[]>("/platform/taxonomy/skills/", { query: { q } }),
  });
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "taxonomy"] });
  const create = useMutation({
    mutationFn: () => api.post<Skill>("/platform/taxonomy/skills/", { name, category }),
    onSuccess: async () => {
      setName("");
      await refresh();
    },
  });
  const publish = useMutation({
    mutationFn: () => api.post<TaxonomyStatus>("/platform/taxonomy/", { notes }),
    onSuccess: async () => {
      setNotes("");
      await refresh();
    },
  });
  const toggle = useMutation({
    mutationFn: (s: Skill) =>
      api.patch<Skill>(`/platform/taxonomy/skills/${s.id}/`, { is_active: !s.is_active }),
    onSuccess: refresh,
  });
  const failure =
    errorText(create.error, t("failed")) ??
    errorText(publish.error, t("failed")) ??
    errorText(toggle.error, t("failed"));
  return (
    <Page title={t("title")} intro={t("intro")}>
      {status.data ? (
        <section aria-labelledby="version" className="flex flex-col gap-2 rounded-lg border p-4">
          <h2 id="version" className="text-lg font-semibold">
            {t("version", { version: status.data.current_version || "—" })}
          </h2>
          <p className="text-sm">
            {t("skillsCount", { count: status.data.skills })}
            {status.data.published_at
              ? ` · ${t("publishedOn", {
                  date: format.dateTime(new Date(status.data.published_at), {
                    dateStyle: "medium",
                  }),
                })}`
              : ""}
          </p>
          {status.data.unpublished_changes ? (
            <p className="text-sm font-medium" role="status">
              {t("unpublished")}
            </p>
          ) : null}
          {isAdmin && status.data.unpublished_changes ? (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                publish.mutate();
              }}
            >
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={ids.notes}>{t("notes")}</Label>
                <Input
                  id={ids.notes}
                  className="h-10 w-80"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </div>
              <Button type="submit" className="h-10" disabled={publish.isPending}>
                {t("publish")}
              </Button>
            </form>
          ) : null}
          <p className="text-muted-foreground text-xs">{t("publishHelp")}</p>
        </section>
      ) : null}
      <form
        role="search"
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQ(search.trim());
        }}
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={ids.q}>{t("search")}</Label>
          <Input
            id={ids.q}
            className="h-10 w-72"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Button type="submit" className="h-10">
          {t("go")}
        </Button>
      </form>
      {isAdmin ? (
        <form
          className="flex flex-wrap items-end gap-2 rounded-md border p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={ids.name}>{t("newSkill")}</Label>
            <Input
              id={ids.name}
              className="h-10"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={ids.cat}>{t("category")}</Label>
            <select
              id={ids.cat}
              className="border-input bg-background h-10 rounded-md border px-2 text-sm"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" className="h-10" disabled={!name.trim() || create.isPending}>
            {t("add")}
          </Button>
        </form>
      ) : null}
      <p aria-live="polite" className="text-destructive text-sm">
        {failure}
      </p>
      {skills.isPending ? (
        <PageSkeleton />
      ) : skills.isError ? (
        <ErrorState error={skills.error} onRetry={() => skills.refetch()} />
      ) : skills.data.length === 0 ? (
        <EmptyState title={t("none")} description={t("noneBody")} />
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {skills.data.map((s) => (
            <SkillRow
              key={s.id}
              skill={s}
              isAdmin={isAdmin}
              onToggle={() => toggle.mutate(s)}
              onChanged={refresh}
            />
          ))}
        </ul>
      )}
      <QualificationAliases isAdmin={isAdmin} />
    </Page>
  );
}

function SkillRow({
  skill: s,
  isAdmin,
  onToggle,
  onChanged,
}: {
  skill: Skill;
  isAdmin: boolean;
  onToggle: () => void;
  onChanged: () => Promise<void>;
}) {
  const t = useTranslations("admin.console.taxonomy");
  const [alias, setAlias] = useState("");
  const id = useId();
  const add = useMutation({
    mutationFn: () => api.post(`/platform/taxonomy/skills/${s.id}/aliases/`, { alias }),
    onSuccess: async () => {
      setAlias("");
      await onChanged();
    },
  });
  const remove = useMutation({
    mutationFn: (aliasId: string) => api.delete(`/platform/taxonomy/aliases/${aliasId}/`),
    onSuccess: onChanged,
  });
  return (
    <li className="flex flex-col gap-1 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{s.canonical_name}</span>
        <Badge variant="secondary">{s.category.replaceAll("_", " ")}</Badge>
        {!s.is_active ? <Badge variant="outline">{t("inactive")}</Badge> : null}
        {isAdmin ? (
          <Button size="sm" variant="ghost" className="ml-auto" onClick={onToggle}>
            {s.is_active ? t("deactivate") : t("activate")}
          </Button>
        ) : null}
      </div>
      <ul aria-label={t("aliasesOf", { name: s.canonical_name })} className="flex flex-wrap gap-1">
        {s.aliases.map((a) => (
          <li key={a.id}>
            <Badge variant="outline">
              {a.alias}
              {isAdmin ? (
                <button
                  type="button"
                  className="ml-1"
                  aria-label={t("removeAlias", { alias: a.alias })}
                  onClick={() => remove.mutate(a.id)}
                >
                  ×
                </button>
              ) : null}
            </Badge>
          </li>
        ))}
      </ul>
      {s.relations.length ? (
        <p className="text-muted-foreground text-xs">
          {s.relations.map((r) => `${r.relation}: ${r.to_skill_name}`).join(" · ")}
        </p>
      ) : null}
      {isAdmin ? (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (alias.trim()) add.mutate();
          }}
        >
          <Label htmlFor={id} className="sr-only">
            {t("newAlias", { name: s.canonical_name })}
          </Label>
          <Input
            id={id}
            className="h-9 w-56"
            placeholder={t("aliasPlaceholder")}
            value={alias}
            onChange={(e) => setAlias(e.target.value)}
          />
          <Button size="sm" type="submit" disabled={!alias.trim() || add.isPending}>
            {t("addAlias")}
          </Button>
          {add.error ? (
            <span className="text-destructive text-xs" role="alert">
              {errorText(add.error, t("failed"))}
            </span>
          ) : null}
        </form>
      ) : null}
    </li>
  );
}

function QualificationAliases({ isAdmin }: { isAdmin: boolean }) {
  const t = useTranslations("admin.console.taxonomy");
  const client = useQueryClient();
  const levels = useQuery({
    queryKey: ["admin", "taxonomy", "qualifications"],
    queryFn: () => api.get<Level[]>("/platform/taxonomy/qualifications/"),
  });
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "taxonomy"] });
  const add = useMutation({
    mutationFn: ({ level, alias }: { level: string; alias: string }) =>
      api.post(`/platform/taxonomy/qualifications/${level}/aliases/`, { alias }),
    onSuccess: async (_d, v) => {
      setDrafts((d) => ({ ...d, [v.level]: "" }));
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/platform/taxonomy/qualification-aliases/${id}/`),
    onSuccess: refresh,
  });
  if (!levels.data) return null;
  return (
    <section aria-labelledby="quals" className="flex flex-col gap-2 rounded-lg border p-4">
      <h2 id="quals" className="text-lg font-semibold">
        {t("qualifications")}
      </h2>
      <ul className="flex flex-col gap-2 text-sm">
        {levels.data.map((l) => (
          <li key={l.id} className="flex flex-col gap-1">
            <span className="font-medium">
              {l.name} <span className="text-muted-foreground">({l.code})</span>
            </span>
            <span className="flex flex-wrap gap-1">
              {l.aliases.map((a) => (
                <Badge key={a.id} variant="outline">
                  {a.alias}
                  {isAdmin ? (
                    <button
                      type="button"
                      className="ml-1"
                      aria-label={t("removeAlias", { alias: a.alias })}
                      onClick={() => remove.mutate(a.id)}
                    >
                      ×
                    </button>
                  ) : null}
                </Badge>
              ))}
            </span>
            {isAdmin ? (
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const alias = (drafts[l.id] ?? "").trim();
                  if (alias) add.mutate({ level: l.id, alias });
                }}
              >
                <Input
                  aria-label={t("newAlias", { name: l.name })}
                  className="h-9 w-56"
                  value={drafts[l.id] ?? ""}
                  onChange={(e) => setDrafts((d) => ({ ...d, [l.id]: e.target.value }))}
                />
                <Button size="sm" type="submit">
                  {t("addAlias")}
                </Button>
              </form>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
