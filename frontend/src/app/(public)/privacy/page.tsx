import type { Metadata } from "next";

import { LegalPage, legalMetadata } from "@/components/legal/legal-page";

export async function generateMetadata(): Promise<Metadata> {
  return legalMetadata("privacyNotice", "/privacy");
}

export default function PrivacyPage() {
  return <LegalPage ns="privacyNotice" />;
}
