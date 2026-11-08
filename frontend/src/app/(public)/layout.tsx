import { cacheLife } from "next/cache";
import type { ReactNode } from "react";

import { PublicFooter } from "@/components/layout/public-footer";
import { PublicHeader } from "@/components/layout/public-header";

async function currentYear(): Promise<number> {
  "use cache";
  cacheLife("days");
  return new Date().getFullYear();
}

export default async function PublicLayout({ children }: { children: ReactNode }) {
  const year = await currentYear();
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <PublicHeader />
      <div className="flex flex-1 flex-col">{children}</div>
      <PublicFooter year={year} />
    </div>
  );
}
