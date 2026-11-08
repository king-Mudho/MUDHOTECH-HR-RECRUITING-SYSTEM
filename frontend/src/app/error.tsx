"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

/** Route-level error boundary (renders inside the root layout) - the "500" page. */
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("states");
  const tc = useTranslations("common");
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <main
      id="main-content"
      className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-4 py-24 text-center"
    >
      <p className="text-destructive text-sm font-semibold">500</p>
      <h1 className="text-3xl font-bold tracking-tight">{t("serverErrorTitle")}</h1>
      <p className="text-muted-foreground">{t("serverErrorBody")}</p>
      {error.digest ? (
        <p className="text-muted-foreground font-mono text-xs">
          {tc("requestId", { id: error.digest })}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button onClick={reset} className="min-h-10">
          {tc("retry")}
        </Button>
        <Button asChild variant="outline" className="min-h-10">
          <Link href="/">{tc("goHome")}</Link>
        </Button>
      </div>
    </main>
  );
}
