"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { meQueryKey, useMe, type MeMembership } from "@/features/auth/session";

import { orgApi, type Role } from "./api";

/**
 * Org-role helpers that mirror backend/apps/organisations/rbac.py for UI *hiding only*.
 * The server is the source of truth and answers 403 for anything not allowed.
 */
const UI_ACTIONS = {
  "org.update": ["org_admin"],
  "policy.view": ["org_admin", "hr_manager"],
  "policy.update": ["org_admin"],
  "structure.manage": ["org_admin", "hr_manager"],
  "members.view": ["org_admin", "hr_manager"],
  "members.manage": ["org_admin"],
  "invitations.manage": ["org_admin"],
} as const satisfies Record<string, readonly Role[]>;

export type UiAction = keyof typeof UI_ACTIONS;

export function can(role: string | null | undefined, action: UiAction): boolean {
  return !!role && (UI_ACTIONS[action] as readonly string[]).includes(role);
}

export const ROLES: Role[] = [
  "org_admin",
  "hr_manager",
  "recruiter",
  "hiring_manager",
  "panelist",
  "auditor",
];

/** The organisation the user is working in: session active org, else their first membership. */
export function useActiveMembership(): {
  membership: MeMembership | null;
  memberships: MeMembership[];
  isPending: boolean;
} {
  const { data: me, isPending } = useMe();
  const memberships = me?.memberships ?? [];
  const membership =
    memberships.find((m) => m.organisation_id === me?.active_organisation_id) ??
    memberships[0] ??
    null;
  return { membership, memberships, isPending };
}

export const orgKeys = {
  org: (id: string) => ["organisations", id] as const,
  policy: (id: string) => ["organisations", id, "policy"] as const,
  departments: (id: string) => ["organisations", id, "departments"] as const,
  locations: (id: string) => ["organisations", id, "locations"] as const,
  members: (id: string) => ["organisations", id, "members"] as const,
  invitations: (id: string) => ["organisations", id, "invitations"] as const,
};

export function useOrganisation(id: string | undefined) {
  return useQuery({
    queryKey: orgKeys.org(id ?? ""),
    queryFn: () => orgApi.get(id!),
    enabled: !!id,
  });
}

export function usePolicy(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: orgKeys.policy(id ?? ""),
    queryFn: () => orgApi.policy(id!),
    enabled: !!id && enabled,
  });
}

export function useDepartments(id: string | undefined) {
  return useQuery({
    queryKey: orgKeys.departments(id ?? ""),
    queryFn: () => orgApi.departments(id!),
    enabled: !!id,
  });
}

export function useLocations(id: string | undefined) {
  return useQuery({
    queryKey: orgKeys.locations(id ?? ""),
    queryFn: () => orgApi.locations(id!),
    enabled: !!id,
  });
}

export function useMembers(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: orgKeys.members(id ?? ""),
    queryFn: () => orgApi.members(id!),
    enabled: !!id && enabled,
  });
}

export function useInvitations(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: orgKeys.invitations(id ?? ""),
    queryFn: () => orgApi.invitations(id!),
    enabled: !!id && enabled,
  });
}

/** Switch the session's active organisation and refresh everything org-dependent. */
export function useSwitchOrganisation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (organisationId: string) => orgApi.setActiveOrg(organisationId),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: meQueryKey });
      await client.invalidateQueries({ queryKey: ["organisations"] });
    },
  });
}
