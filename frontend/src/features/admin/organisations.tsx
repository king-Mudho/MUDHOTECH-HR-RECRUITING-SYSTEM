"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { EmptyState, ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMe } from "@/features/auth/session";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

type PlatformOrganisation = components["schemas"]["PlatformOrganisation"];
type Page = { count: number; results: PlatformOrganisation[] };
type Action = "verify" | "suspend" | "reactivate";

const FILTERS = ["", "pending_verification", "active", "suspended", "closed"] as const;

export function AdminOrganisations() {
  const t = useTranslations("admin.organisations");
  const ts = useTranslations("status");
  const { data: me } = useMe();
  const isAdmin = me?.platform_role === "platform_admin";
  const [status, setStatus] = useState<(typeof FILTERS)[number]>("pending_verification");
  const [search, setSearch] = useState("");
  const [pending, setPending] = useState<{ org: PlatformOrganisation; action: Action } | null>(
    null,
  );
  const client = useQueryClient();

  const query = useQuery({
    queryKey: ["admin", "organisations", status, search],
    queryFn: () =>
      api.get<Page>("/platform/organisations/", {
        query: { status: status || undefined, search: search || undefined, page_size: 50 },
      }),
  });
  const act = useMutation({
    mutationFn: ({ id, action, reason }: { id: string; action: Action; reason: string }) =>
      api.post<PlatformOrganisation>(`/platform/organisations/${id}/${action}/`, { reason }),
    onSuccess: () => {
      setPending(null);
      client.invalidateQueries({ queryKey: ["admin", "organisations"] });
    },
  });

  const statusLabel = (s: string) => (ts.has(s) ? ts(s) : s.replaceAll("_", " "));

  return (
    <main id="main-content" className="flex flex-col gap-6 p-4 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground">{isAdmin ? t("subtitle") : t("subtitleReadOnly")}</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div role="group" aria-label={t("filterLabel")} className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <Button
              key={f || "all"}
              variant={status === f ? "default" : "outline"}
              size="sm"
              className="min-h-8"
              aria-pressed={status === f}
              onClick={() => setStatus(f)}
            >
              {f ? statusLabel(f) : t("all")}
            </Button>
          ))}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="org-search">{t("search")}</Label>
          <Input
            id="org-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-10 w-64"
          />
        </div>
      </div>

      {query.isPending ? (
        <PageSkeleton rows={4} />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : query.data.results.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{t("title")}</caption>
            <thead className="bg-muted/50">
              <tr>
                <th scope="col" className="p-3">
                  {t("name")}
                </th>
                <th scope="col" className="p-3">
                  {t("status")}
                </th>
                <th scope="col" className="p-3">
                  {t("members")}
                </th>
                <th scope="col" className="p-3">
                  {t("created")}
                </th>
                <th scope="col" className="p-3">
                  <span className="sr-only">{t("actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((org) => (
                <tr key={org.id} className="border-t">
                  <td className="p-3">
                    <div className="font-medium">{org.name}</div>
                    <div className="text-muted-foreground text-xs">
                      {[org.city, org.industry, org.registration_number]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                  </td>
                  <td className="p-3">
                    <StatusBadge status={org.status ?? "unknown"} />
                  </td>
                  <td className="p-3">{org.member_count}</td>
                  <td className="p-3">{new Date(org.created_at).toLocaleDateString()}</td>
                  <td className="p-3 text-right">
                    {isAdmin ? (
                      <div className="flex justify-end gap-2">
                        {org.status === "pending_verification" ? (
                          <Button
                            size="sm"
                            className="min-h-8"
                            onClick={() => setPending({ org, action: "verify" })}
                          >
                            {t("verify")}
                          </Button>
                        ) : null}
                        {org.status === "active" || org.status === "pending_verification" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="min-h-8"
                            onClick={() => setPending({ org, action: "suspend" })}
                          >
                            {t("suspend")}
                          </Button>
                        ) : null}
                        {org.status === "suspended" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="min-h-8"
                            onClick={() => setPending({ org, action: "reactivate" })}
                          >
                            {t("reactivate")}
                          </Button>
                        ) : null}
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => !open && setPending(null)}
        title={pending ? t(`${pending.action}Title`, { name: pending.org.name }) : ""}
        description={pending ? t(`${pending.action}Body`) : undefined}
        confirmLabel={pending ? t(pending.action) : ""}
        destructive={pending?.action === "suspend"}
        reason={pending?.action === "suspend" ? "required" : "optional"}
        pending={act.isPending}
        error={act.error instanceof ApiError ? act.error.message : act.isError ? t("error") : null}
        onConfirm={(reason) =>
          pending && act.mutate({ id: pending.org.id, action: pending.action, reason })
        }
      />
    </main>
  );
}
