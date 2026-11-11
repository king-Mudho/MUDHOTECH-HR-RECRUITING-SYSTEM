"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { EmptyState, ErrorState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

import { notificationKeys } from "./bell";

type Item = components["schemas"]["InboxItem"];
type Page = components["schemas"]["PaginatedInboxItemList"];
const PAGE_SIZE = 20;

/** Full notification centre (P05-T09): every in-app notification, newest first, paged. */
export function NotificationCentre() {
  const t = useTranslations("notifications");
  const format = useFormatter();
  const client = useQueryClient();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [page, setPage] = useState(1);
  const list = useQuery({
    queryKey: ["notifications", "centre", unreadOnly, page],
    queryFn: () =>
      api.get<Page>("/notifications/", {
        query: { page, page_size: PAGE_SIZE, ...(unreadOnly ? { unread: "1" } : {}) },
      }),
  });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["notifications"] });
    void client.invalidateQueries({ queryKey: notificationKeys.unread });
  };
  const markRead = useMutation({
    mutationFn: (id: string) => api.post<Item>(`/notifications/${id}/read/`),
    onSuccess: refresh,
  });
  const markAll = useMutation({
    mutationFn: () => api.post<{ count: number }>("/notifications/read-all/"),
    onSuccess: refresh,
  });
  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.count / PAGE_SIZE)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <Button
          type="button"
          variant="outline"
          className="min-h-10"
          disabled={markAll.isPending}
          onClick={() => markAll.mutate()}
        >
          {t("markAll")}
        </Button>
      </div>
      <div role="group" aria-label={t("filterLabel")} className="flex gap-1.5">
        {[false, true].map((only) => (
          <Button
            key={String(only)}
            type="button"
            size="sm"
            variant={unreadOnly === only ? "default" : "outline"}
            aria-pressed={unreadOnly === only}
            className="min-h-9"
            onClick={() => {
              setUnreadOnly(only);
              setPage(1);
            }}
          >
            {only ? t("filterUnread") : t("filterAll")}
          </Button>
        ))}
      </div>
      {list.isPending ? (
        <PageSkeleton rows={4} />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.data.results.length === 0 ? (
        <EmptyState
          title={t("emptyTitle")}
          description={unreadOnly ? t("emptyUnread") : t("empty")}
        />
      ) : (
        <>
          <ul className="flex flex-col divide-y rounded-lg border" aria-live="polite">
            {list.data.results.map((n) => (
              <li key={n.id} className="flex flex-col gap-1 p-3">
                <p className={n.read_at ? "text-sm" : "text-sm font-medium"}>
                  {!n.read_at ? <span className="sr-only">{t("unreadPrefix")} </span> : null}
                  {n.text}
                </p>
                <div className="text-muted-foreground flex flex-wrap items-center gap-3 text-xs">
                  <time dateTime={n.created_at}>
                    {format.dateTime(new Date(n.created_at), {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </time>
                  {n.link ? (
                    <Link
                      href={n.link}
                      className="text-foreground underline"
                      onClick={() => !n.read_at && markRead.mutate(n.id)}
                    >
                      {t("open")}
                    </Link>
                  ) : null}
                  {!n.read_at ? (
                    <button
                      type="button"
                      className="text-foreground min-h-6 underline"
                      onClick={() => markRead.mutate(n.id)}
                    >
                      {t("markRead")}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          {totalPages > 1 ? (
            <nav
              aria-label={t("pagination")}
              className="flex items-center justify-between gap-2 text-sm"
            >
              <span>{t("pageOf", { page, total: totalPages })}</span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  {t("previous")}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                >
                  {t("next")}
                </Button>
              </div>
            </nav>
          ) : null}
        </>
      )}
    </div>
  );
}
