"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import type { components } from "@/types/api";

type Item = components["schemas"]["InboxItem"];
type Page = components["schemas"]["PaginatedInboxItemList"];

export const POLL_MS = 30_000;
export const notificationKeys = {
  unread: ["notifications", "unread"] as const,
  latest: ["notifications", "latest"] as const,
};

/** Bell with unread count (polled every 30 s while the tab is visible) and a panel of the latest items. */
export function NotificationBell() {
  const t = useTranslations("notifications");
  const format = useFormatter();
  const client = useQueryClient();
  const panelId = useId();
  const root = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  const unread = useQuery({
    queryKey: notificationKeys.unread,
    queryFn: () => api.get<{ count: number }>("/notifications/unread-count/"),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    retry: false,
  });
  const latest = useQuery({
    queryKey: notificationKeys.latest,
    queryFn: () => api.get<Page>("/notifications/", { query: { page_size: 10 } }),
    enabled: open,
  });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: notificationKeys.unread });
    void client.invalidateQueries({ queryKey: notificationKeys.latest });
  };
  const markRead = useMutation({
    mutationFn: (id: string) => api.post<Item>(`/notifications/${id}/read/`),
    onSuccess: refresh,
  });
  const markAll = useMutation({
    mutationFn: () => api.post<{ count: number }>("/notifications/read-all/"),
    onSuccess: refresh,
  });

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const count = unread.data?.count ?? 0;
  const items = latest.data?.results ?? [];
  return (
    <div ref={root} className="relative">
      <Button
        variant="ghost"
        size="icon"
        className="relative size-10"
        aria-label={count > 0 ? t("bellUnread", { count }) : t("bell")}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <Bell aria-hidden="true" />
        {count > 0 ? (
          <span
            aria-hidden="true"
            className="bg-destructive absolute top-1.5 right-1.5 grid min-w-4 place-items-center rounded-full px-1 text-[10px] leading-4 font-semibold text-white"
          >
            {count > 99 ? "99+" : count}
          </span>
        ) : null}
      </Button>
      {open ? (
        <section
          id={panelId}
          aria-label={t("title")}
          className="bg-popover text-popover-foreground absolute right-0 z-40 mt-2 flex max-h-[70vh] w-[min(22rem,calc(100vw-2rem))] flex-col rounded-lg border shadow-lg"
        >
          <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
            <h2 className="text-sm font-semibold">{t("title")}</h2>
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto p-0"
              disabled={count === 0 || markAll.isPending}
              onClick={() => markAll.mutate()}
            >
              {t("markAll")}
            </Button>
          </div>
          <div className="overflow-y-auto" aria-live="polite">
            {latest.isPending ? (
              <p className="text-muted-foreground p-3 text-sm">{t("loading")}</p>
            ) : latest.isError ? (
              <p role="alert" className="p-3 text-sm">
                {t("failed")}
              </p>
            ) : items.length === 0 ? (
              <p className="text-muted-foreground p-3 text-sm">{t("empty")}</p>
            ) : (
              <ul>
                {items.map((n) => (
                  <li key={n.id} className="flex flex-col gap-1 border-b px-3 py-2 last:border-b-0">
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
                          onClick={() => {
                            if (!n.read_at) markRead.mutate(n.id);
                            setOpen(false);
                          }}
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
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}
