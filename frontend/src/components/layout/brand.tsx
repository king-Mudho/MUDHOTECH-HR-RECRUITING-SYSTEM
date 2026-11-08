import Link from "next/link";

import { cn } from "@/lib/utils";

/** Text logo: "MUDHOTECH HR RECRUITING SYSTEM" (full name on wide screens, MHRS on narrow). */
export function Brand({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link
      href={href}
      className={cn("text-foreground flex min-h-6 items-center gap-2 font-semibold", className)}
    >
      <span
        aria-hidden="true"
        className="bg-primary text-primary-foreground grid size-8 place-items-center rounded-md text-sm font-bold"
      >
        M
      </span>
      <span className="hidden text-sm tracking-tight sm:inline">
        MUDHOTECH HR RECRUITING SYSTEM
      </span>
      <span className="text-sm tracking-tight sm:hidden">MHRS</span>
    </Link>
  );
}
