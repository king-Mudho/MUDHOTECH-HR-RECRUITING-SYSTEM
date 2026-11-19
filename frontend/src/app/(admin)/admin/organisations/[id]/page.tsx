import { Suspense } from "react";

import { PageSkeleton } from "@/components/states/page-skeleton";
import { AdminOrganisationDetailRoute } from "@/features/admin/console";

export default function Page() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <AdminOrganisationDetailRoute />
    </Suspense>
  );
}
