import type { NavItem } from "./nav-types";

export const CANDIDATE_NAV: NavItem[] = [
  { href: "/candidate/dashboard", labelKey: "dashboard", icon: "dashboard" },
  { href: "/candidate/applications", labelKey: "applications", icon: "applications" },
  { href: "/candidate/profile", labelKey: "profile", icon: "profile" },
  { href: "/candidate/documents", labelKey: "documents", icon: "documents" },
  { href: "/candidate/privacy", labelKey: "privacy", icon: "privacy" },
  { href: "/candidate/settings", labelKey: "settings", icon: "settings" },
];

export const HR_NAV: NavItem[] = [
  { href: "/hr/dashboard", labelKey: "dashboard", icon: "dashboard" },
  { href: "/hr/jobs", labelKey: "jobs", icon: "jobs" },
  { href: "/hr/reports", labelKey: "reports", icon: "reports" },
  { href: "/hr/settings", labelKey: "settings", icon: "settings" },
];

export const ADMIN_NAV: NavItem[] = [
  { href: "/admin/dashboard", labelKey: "dashboard", icon: "dashboard" },
  { href: "/admin/organisations", labelKey: "organisations", icon: "organisations" },
  { href: "/admin/users", labelKey: "users", icon: "users" },
  { href: "/admin/feature-flags", labelKey: "featureFlags", icon: "flags" },
  { href: "/admin/system-health", labelKey: "systemHealth", icon: "health" },
  { href: "/admin/dead-letters", labelKey: "deadLetters", icon: "deadLetters" },
  { href: "/admin/audit-logs", labelKey: "auditLogs", icon: "audit" },
];
