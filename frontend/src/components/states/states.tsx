"use client";

import { AlertTriangle, Inbox, Lock, RotateCcw } from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

interface StateProps {
  title?: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

function StateFrame({
  icon,
  title,
  description,
  action,
  className,
  role,
}: StateProps & { icon: ReactNode; title: string; role?: "alert" | "status" }) {
  return (
    <div
      role={role}
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-12 text-center",
        className,
      )}
    >
      <div className="bg-muted text-muted-foreground grid size-12 place-items-center rounded-full">
        {icon}
      </div>
      <h2 className="text-lg font-semibold">{title}</h2>
      {description ? (
        <div className="text-muted-foreground max-w-md text-sm">{description}</div>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

/** Empty data view - always suggest the next action. */
export function EmptyState({ title, description, action, className }: StateProps) {
  const t = useTranslations("states");
  return (
    <StateFrame
      icon={<Inbox aria-hidden="true" />}
      title={title ?? t("emptyTitle")}
      description={description}
      action={action}
      className={className}
    />
  );
}

/** Error view with retry and the request id so support can trace the failure. */
export function ErrorState({
  title,
  description,
  error,
  requestId,
  onRetry,
  className,
}: StateProps & { error?: unknown; requestId?: string | null; onRetry?: () => void }) {
  const t = useTranslations("states");
  const tc = useTranslations("common");
  const rid = requestId ?? (error instanceof ApiError ? error.requestId : null);
  const message = description ?? (error instanceof ApiError ? error.message : t("errorBody"));
  return (
    <StateFrame
      role="alert"
      icon={<AlertTriangle aria-hidden="true" />}
      title={title ?? t("errorTitle")}
      description={
        <>
          <p>{message}</p>
          {rid ? (
            <p className="mt-2 font-mono text-xs" data-testid="request-id">
              {tc("requestId", { id: rid })}
            </p>
          ) : null}
        </>
      }
      action={
        onRetry ? (
          <Button onClick={onRetry} variant="outline" className="min-h-10">
            <RotateCcw aria-hidden="true" />
            {tc("retry")}
          </Button>
        ) : null
      }
      className={className}
    />
  );
}

/** Permission-denied view (403). The server enforces permissions; the UI only explains. */
export function ForbiddenState({ title, description, action, className }: StateProps) {
  const t = useTranslations("states");
  return (
    <StateFrame
      role="alert"
      icon={<Lock aria-hidden="true" />}
      title={title ?? t("forbiddenTitle")}
      description={description}
      action={action}
      className={className}
    />
  );
}
