"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { meQueryKey, useMe } from "@/features/auth/session";

import { orgApi } from "../api";
import { OrganisationForm } from "./organisation-form";

/** Employer sign-up step (SRS §3.1): signed-in, verified user creates an organisation. */
export function CreateOrganisation() {
  const t = useTranslations("organisations.create");
  const { data: me, isPending } = useMe();
  const router = useRouter();
  const queryClient = useQueryClient();

  if (isPending) return <PageSkeleton rows={4} />;
  if (!me) {
    return (
      <div className="flex flex-col gap-3">
        <p>{t("signInFirst")}</p>
        <div className="flex flex-wrap gap-2">
          <Button asChild className="min-h-10">
            <Link href="/register">{t("createAccount")}</Link>
          </Button>
          <Button asChild variant="outline" className="min-h-10">
            <Link href="/login?next=/employers">{t("signIn")}</Link>
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <Alert>
        <AlertDescription>{t("verificationNotice")}</AlertDescription>
      </Alert>
      <OrganisationForm
        submitLabel={t("submit")}
        onSubmit={async (values) => {
          const org = await orgApi.create(values);
          await orgApi.setActiveOrg(org.id);
          await queryClient.invalidateQueries({ queryKey: meQueryKey });
          router.push("/hr/settings/organisation");
        }}
      />
    </div>
  );
}
