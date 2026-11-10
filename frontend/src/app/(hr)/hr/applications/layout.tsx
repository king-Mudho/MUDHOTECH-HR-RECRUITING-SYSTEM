import type { ReactNode } from "react";

/** Application pages share the main landmark (skip-link target) and page padding. */
export default function ApplicationsLayout({ children }: { children: ReactNode }) {
  return (
    <main id="main-content" className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4 sm:p-6">
      {children}
    </main>
  );
}
