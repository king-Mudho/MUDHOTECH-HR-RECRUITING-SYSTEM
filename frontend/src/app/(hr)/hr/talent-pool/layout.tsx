import type { ReactNode } from "react";

/** Talent pool pages share the main landmark (skip-link target) and page padding. */
export default function TalentPoolLayout({ children }: { children: ReactNode }) {
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:p-6">
      {children}
    </main>
  );
}
