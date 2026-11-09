import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { LoginForm } from "@/features/auth/components/login-form";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.titles");
  return { title: t("signIn"), robots: { index: false } };
}

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton rows={3} />}>
      <LoginForm />
    </Suspense>
  );
}
