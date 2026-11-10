"use client";

import { Check, Link2, Mail, MessageCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";

/**
 * The deadline in the viewer's own timezone (EC-JOB-05). Rendered after hydration so the server
 * never guesses the visitor's zone; the vacancy-zone time is always shown by the server.
 */
const noopSubscribe = () => () => {};

export function ViewerLocalTime({ iso, jobTimeZone }: { iso: string; jobTimeZone: string }) {
  const t = useTranslations("publicJobs.detail");
  // Server snapshot is null, so the server never guesses the visitor's zone.
  const viewerZone = useSyncExternalStore(
    noopSubscribe,
    () => Intl.DateTimeFormat().resolvedOptions().timeZone,
    () => null,
  );
  if (!viewerZone || viewerZone === jobTimeZone) return null;
  const formatted = new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
  return (
    <span className="text-muted-foreground block text-sm">
      {t("yourTime", { time: formatted, zone: viewerZone })}
    </span>
  );
}

/** Share links (WhatsApp first: the most common channel for job sharing in Zimbabwe). */
export function ShareButtons({ url, title }: { url: string; title: string }) {
  const t = useTranslations("publicJobs.share");
  const [copied, setCopied] = useState(false);
  const text = encodeURIComponent(`${title} ${url}`);
  const links = [
    {
      key: "whatsapp",
      href: `https://wa.me/?text=${text}`,
      icon: <MessageCircle aria-hidden="true" />,
    },
    {
      key: "linkedin",
      href: `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`,
      icon: null,
    },
    {
      key: "email",
      href: `mailto:?subject=${encodeURIComponent(title)}&body=${encodeURIComponent(url)}`,
      icon: <Mail aria-hidden="true" />,
    },
  ];
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("label")}>
      {links.map((l) => (
        <Button key={l.key} asChild variant="outline" size="sm" className="min-h-9">
          <a href={l.href} target="_blank" rel="noopener noreferrer">
            {l.icon}
            {t(l.key)}
          </a>
        </Button>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="min-h-9"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(url);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          } catch {
            setCopied(false);
          }
        }}
      >
        {copied ? <Check aria-hidden="true" /> : <Link2 aria-hidden="true" />}
        <span aria-live="polite">{copied ? t("copied") : t("copy")}</span>
      </Button>
    </div>
  );
}
