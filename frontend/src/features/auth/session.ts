"use client";

import { type QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api-client";
import type { components } from "@/types/api";

import { authApi } from "./allauth";

export type Me = components["schemas"]["Me"];
export type MeMembership = components["schemas"]["MeMembership"];

export const meQueryKey = ["auth", "me"] as const;

/** Current user from `/api/v1/me/`; `null` when signed out (401/403). */
export async function fetchMe(): Promise<Me | null> {
  try {
    return await api.get<Me>("/me/");
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return null;
    throw err;
  }
}

export function useMe() {
  return useQuery({ queryKey: meQueryKey, queryFn: fetchMe, staleTime: 60_000 });
}

export function useRefreshMe() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: meQueryKey });
}

export function useLogout() {
  const client = useQueryClient();
  return async () => {
    await authApi.logout();
    client.clear();
  };
}

export type Area = "candidate" | "hr" | "admin" | "account";

/** UI-only gating (the server enforces): which areas may this user enter? */
export function canEnter(me: Me | null | undefined, area: Area): boolean {
  if (!me) return false;
  switch (area) {
    case "hr":
      return me.memberships.length > 0;
    case "admin":
      return me.platform_role === "platform_admin" || me.platform_role === "platform_support";
    case "candidate":
    case "account":
      return true;
  }
}

/** Where to send a user after sign-in when no `next` is given. */
export function homeFor(me: Me | null | undefined): string {
  if (!me) return "/login";
  if (me.platform_role === "platform_admin" || me.platform_role === "platform_support") {
    return "/admin/dashboard";
  }
  if (me.memberships.length > 0) return "/hr/dashboard";
  return "/candidate/dashboard";
}

/** Only allow same-site relative redirects (prevents open redirects via ?next=). */
export function safeNext(next: string | null | undefined): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return null;
  }
  return next;
}

/**
 * Fetch `/me` fresh after the session changed (login, verification, accepting an invitation).
 * Cancels in-flight `/me` requests first: those started before the session changed would resolve
 * with the old (signed-out) answer and be reused by react-query's request de-duplication.
 */
export async function reloadMe(client: QueryClient): Promise<Me | null> {
  await client.cancelQueries({ queryKey: meQueryKey });
  const me = await fetchMe();
  client.setQueryData(meQueryKey, me);
  return me;
}
