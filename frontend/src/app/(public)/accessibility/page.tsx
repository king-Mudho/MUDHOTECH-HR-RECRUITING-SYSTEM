import type { Metadata } from "next";

import { LegalPage, legalMetadata } from "@/components/legal/legal-page";

export async function generateMetadata(): Promise<Metadata> {
  return legalMetadata("accessibilityStatement", "/accessibility");
}

export default function AccessibilityPage() {
  return <LegalPage ns="accessibilityStatement" />;
}
