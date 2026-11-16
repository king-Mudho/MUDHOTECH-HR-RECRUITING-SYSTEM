"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

import { hrApplicationKeys } from "./api";

type Reveal = components["schemas"]["IdentityReveal"];

/** Blind review (P08-T04): identity stays hidden until this reviewer gives a reason. */
export function RevealIdentity({ applicationId }: { applicationId: string }) {
  const t = useTranslations("hrApplications.blind");
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const reasonId = useId();
  const reveal = useMutation({
    mutationFn: () =>
      api.post<Reveal>(
        `/hr/applications/${applicationId}/reveal-identity/`,
        { reason },
        { orgId: orgId! },
      ),
    onSuccess: () => {
      void client.invalidateQueries({
        queryKey: hrApplicationKeys.detail(orgId ?? "", applicationId),
      });
    },
  });
  const error =
    reveal.error instanceof ApiError ? reveal.error.message : reveal.error ? t("failed") : null;
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p>{t("hidden")}</p>
      {open ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            reveal.mutate();
          }}
        >
          <Label htmlFor={reasonId}>{t("reason")}</Label>
          <Input
            id={reasonId}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            aria-describedby={`${reasonId}-hint`}
          />
          <p id={`${reasonId}-hint`} className="text-muted-foreground text-xs">
            {t("reasonHint")}
          </p>
          {error ? (
            <p role="alert" className="text-destructive text-xs">
              {error}
            </p>
          ) : null}
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={reveal.isPending || reason.trim().length < 5}>
              {t("confirm")}
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => setOpen(false)}>
              {t("cancel")}
            </Button>
          </div>
        </form>
      ) : (
        <Button size="sm" variant="outline" className="self-start" onClick={() => setOpen(true)}>
          {t("reveal")}
        </Button>
      )}
    </div>
  );
}
