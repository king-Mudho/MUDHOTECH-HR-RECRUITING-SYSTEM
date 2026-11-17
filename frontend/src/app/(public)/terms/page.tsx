import type { Metadata } from "next";

import { LegalPage, legalMetadata } from "@/components/legal/legal-page";

export async function generateMetadata(): Promise<Metadata> {
  return legalMetadata("termsPage", "/terms");
}

export default function TermsPage() {
  return <LegalPage ns="termsPage" />;
}
