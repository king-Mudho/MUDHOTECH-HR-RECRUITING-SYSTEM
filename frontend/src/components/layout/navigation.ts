import type { NavItem } from "./nav-types";

export const CANDIDATE_NAV: NavItem[] = [
  { href: "/candidate/dashboard", labelKey: "dashboard", icon: "dashboard" },
  { href: "/candidate/applications", labelKey: "applications", icon: "applications" },
  { href: "/candidate/profile", labelKey: "profile", icon: "profile" },
  { href: "/candidate/documents", labelKey: "documents", icon: "documents" },
  { href: "/candidate/privacy", labelKey: "privacy", icon: "privacy" },
  { href: "/candidate/settings", labelKey: "settings", icon: "settings" },
];

// Reports (/hr/reports) is added with its page in Phase 13 (P13-T05). Nav items only link to
// pages that exist (tests/navigation.test.ts).
export const HR_NAV: NavItem[] = [
  { href: "/hr/dashboard", labelKey: "dashboard", icon: "dashboard" },
  { href: "/hr/jobs", labelKey: "jobs", icon: "jobs" },
  { href: "/hr/interviews", labelKey: "interviews", icon: "interviews" },
  { href: "/hr/offers", labelKey: "offers", icon: "offers" },
  { href: "/hr/settings", labelKey: "settings", icon: "settings" },
];

// Platform users, feature flags, system health, dead letters and platform audit logs are not
// built yet (DEFECT_LOG D-002); they use Django admin / Flower / ops tooling until then.
export const ADMIN_NAV: NavItem[] = [
  { href: "/admin/dashboard", labelKey: "dashboard", icon: "dashboard" },
  { href: "/admin/organisations", labelKey: "organisations", icon: "organisations" },
  { href: "/admin/support-access", labelKey: "supportAccess", icon: "audit" },
  { href: "/admin/model-registry", labelKey: "modelRegistry", icon: "flags" },
];
