"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { Button } from "@/components/ui/button";
import { useJobsContext } from "@/features/jobs/hooks";
import { ApiError, api } from "@/lib/api-client";

/** "I know this applicant" (EC-REV-11): the application leaves this reviewer's lists. */
export function DeclareConflict({
  applicationId,
  jobId,
}: {
  applicationId: string;
  jobId: string;
}) {
  const t = useTranslations("hrApplications.conflict");
  const { orgId } = useJobsContext();
  const client = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const declare = useMutation({
    mutationFn: (reason: string) =>
      api.post(
        `/hr/applications/${applicationId}/declare-conflict/`,
        { reason },
        { orgId: orgId! },
      ),
    onSuccess: () => {
      setOpen(false);
      void client.invalidateQueries({ queryKey: ["hr-applications", orgId ?? ""] });
      router.push(`/hr/jobs/${jobId}/applications`);
    },
  });
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        {t("action")}
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={t("title")}
        description={t("description")}
        confirmLabel={t("confirm")}
        reason="required"
        pending={declare.isPending}
        error={
          declare.error instanceof ApiError
            ? declare.error.message
            : declare.error
              ? t("failed")
              : null
        }
        onConfirm={(reason) => declare.mutate(reason)}
      />
    </>
  );
}
