"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AuthCard } from "@/features/auth/components/auth-card";
import { meQueryKey, useMe } from "@/features/auth/session";
import { ApiError } from "@/lib/api-client";

import { orgApi } from "../api";

/** /invitations/[token]: preview, then accept as the signed-in invitee (EC-ORG-04, EC-ORG-05). */
export function InvitationAccept() {
  const t = useTranslations("organisations.invitation");
  const tr = useTranslations("roles");
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: me, isPending: mePending } = useMe();
  const preview = useQuery({
    queryKey: ["invitations", token],
    queryFn: () => orgApi.previewInvitation(token),
    retry: false,
  });
  const accept = useMutation({
    mutationFn: async () => {
      const membership = await orgApi.acceptInvitation(token);
      await orgApi.setActiveOrg(membership.organisation_id); // work in the org just joined
      return membership;
    },
  });

  if (preview.isPending || mePending) return <PageSkeleton rows={3} />;
  if (preview.isError) {
    return (
      <AuthCard title={t("invalidTitle")}>
        <Alert variant="destructive">
          <AlertDescription>{t("invalidBody")}</AlertDescription>
        </Alert>
      </AuthCard>
    );
  }
  const inv = preview.data;
  const next = encodeURIComponent(`/invitations/${token}`);
  if (inv.status !== "pending") {
    return (
      <AuthCard title={t("unavailableTitle")}>
        <Alert variant="destructive">
          <AlertDescription>{t(`status_${inv.status}`)}</AlertDescription>
        </Alert>
      </AuthCard>
    );
  }
  if (accept.isSuccess) {
    return (
      <AuthCard title={t("acceptedTitle", { org: inv.organisation_name })}>
        <p role="status">{t("acceptedBody")}</p>
        <Button
          className="min-h-10"
          onClick={async () => {
            await queryClient.invalidateQueries({ queryKey: meQueryKey });
            router.push("/hr/dashboard");
          }}
        >
          {t("goToDashboard")}
        </Button>
      </AuthCard>
    );
  }
  const errorText =
    accept.error instanceof ApiError
      ? accept.error.message
      : accept.isError
        ? t("genericError")
        : null;
  return (
    <AuthCard
      title={t("title", { org: inv.organisation_name })}
      description={t("body", { role: tr(inv.role), email: inv.email_hint })}
    >
      {errorText ? (
        <Alert variant="destructive">
          <AlertDescription>{errorText}</AlertDescription>
        </Alert>
      ) : null}
      {me ? (
        <>
          <p className="text-muted-foreground text-sm">{t("signedInAs", { email: me.email })}</p>
          <Button className="min-h-10" disabled={accept.isPending} onClick={() => accept.mutate()}>
            {t("accept")}
          </Button>
        </>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button asChild className="min-h-10">
            <Link href={`/login?next=${next}`}>{t("signIn")}</Link>
          </Button>
          <Button asChild variant="outline" className="min-h-10">
            <Link href="/register">{t("createAccount")}</Link>
          </Button>
        </div>
      )}
    </AuthCard>
  );
}
