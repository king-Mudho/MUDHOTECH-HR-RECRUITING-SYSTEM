"use client";

import { useParams } from "next/navigation";

import { JobOverview } from "./job-overview";
import { JobWizard } from "./wizard";

/** Route-level client wrappers that read the dynamic `[id]` segment. */
export function JobOverviewRoute() {
  const { id } = useParams<{ id: string }>();
  return <JobOverview jobId={id} />;
}

export function JobEditRoute() {
  const { id } = useParams<{ id: string }>();
  return <JobWizard jobId={id} />;
}
