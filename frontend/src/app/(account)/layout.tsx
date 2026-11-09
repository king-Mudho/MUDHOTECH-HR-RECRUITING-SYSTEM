import type { ReactNode } from "react";

import { PublicHeader } from "@/components/layout/public-header";
import { AuthGate } from "@/features/auth/components/auth-gate";

/** Account area shared by every signed-in user (candidates and staff). */
export default function AccountLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <PublicHeader />
      <AuthGate area="account">{children}</AuthGate>
    </div>
  );
}
