/** Navigation item; `labelKey` is a key in the `nav` messages namespace. */
export interface NavItem {
  href: string;
  labelKey: string;
  icon?: NavIcon;
}

export type NavIcon =
  | "dashboard"
  | "jobs"
  | "applications"
  | "profile"
  | "documents"
  | "settings"
  | "privacy"
  | "reports"
  | "organisations"
  | "users"
  | "flags"
  | "health"
  | "deadLetters"
  | "audit";
