import type { ReactNode } from "react";

/** Placeholder layout for the (candidate) route group; the full shell is built in P01-T13. */
export default function Layout({ children }: { children: ReactNode }) {
  return <div className="flex min-h-full flex-1 flex-col">{children}</div>;
}
