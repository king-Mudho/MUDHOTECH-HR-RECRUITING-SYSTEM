import { z } from "zod";

const optionalUrl = z
  .string()
  .trim()
  .refine((v) => v === "" || /^https?:\/\/[^\s]+\.[^\s]+$/i.test(v), "invalidUrl");

export const organisationSchema = z.object({
  name: z.string().trim().min(2, "required").max(200),
  legal_name: z.string().trim().max(255),
  registration_number: z.string().trim().max(100),
  industry: z.string().trim().max(100),
  size_band: z.enum(["", "1-9", "10-49", "50-249", "250-999", "1000+"]),
  country: z.string().trim().length(2, "invalidCountry"),
  city: z.string().trim().max(100),
  website: optionalUrl,
  description: z.string().max(5000),
});

export type OrganisationValues = z.infer<typeof organisationSchema>;

export const ORG_DEFAULTS: OrganisationValues = {
  name: "",
  legal_name: "",
  registration_number: "",
  industry: "",
  size_band: "",
  country: "ZW",
  city: "",
  website: "",
  description: "",
};

export const inviteSchema = z.object({
  email: z.string().trim().min(1, "required").email("invalidEmail"),
  role: z.enum(["org_admin", "hr_manager", "recruiter", "hiring_manager", "panelist", "auditor"]),
});
export type InviteValues = z.infer<typeof inviteSchema>;

export const policySchema = z.object({
  privacy_notice: z.string().max(20000),
  retention_months: z
    .number({ message: "required" })
    .int()
    .min(1, "outOfRange")
    .max(120, "outOfRange"),
  duplicate_policy: z.enum(["one_active", "allow_resubmit_replace", "allow_multiple"]),
  shortlist_dual_control: z.boolean(),
  rubric_dual_control: z.boolean(),
  ai_enabled: z.boolean(),
  llm_enabled: z.boolean(),
  blind_review_default: z.boolean(),
  notification_delay_minutes: z
    .number({ message: "required" })
    .int()
    .min(0, "outOfRange")
    .max(1440, "outOfRange"),
  hide_ai_from_panelists: z.boolean(),
  rights_request_sla_days: z
    .number({ message: "required" })
    .int()
    .min(1, "outOfRange")
    .max(90, "outOfRange"),
});
export type PolicyValues = z.infer<typeof policySchema>;
