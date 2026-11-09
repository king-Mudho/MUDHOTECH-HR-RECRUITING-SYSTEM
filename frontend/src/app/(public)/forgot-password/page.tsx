import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { ForgotPasswordForm } from "@/features/auth/components/password-reset";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.titles");
  return { title: t("forgotPassword"), robots: { index: false } };
}

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton rows={3} />}>
      <ForgotPasswordForm />
    </Suspense>
  );
}
