import type { ReactNode } from "react";

/** Candidate pages share the main landmark (skip-link target) and page padding. */
export default function CandidatePagesLayout({ children }: { children: ReactNode }) {
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-4xl flex-col gap-6 p-4 sm:p-6">
      {children}
    </main>
  );
}
