import { api, apiRequest } from "@/lib/api-client";
import type { components } from "@/types/api";

type S = components["schemas"];
export type Organisation = S["Organisation"];
export type OrganisationCreate = S["OrganisationCreateRequest"];
export type OrganisationPatch = S["PatchedOrganisationRequest"];
export type Policy = S["Policy"];
export type PolicyPatch = S["PatchedPolicyRequest"];
export type Department = S["Department"];
export type Location = S["Location"];
export type Membership = S["Membership"];
export type Invitation = S["Invitation"];
export type InvitationCreate = S["InvitationCreateRequest"];
export type InvitationPublic = S["InvitationPublic"];
export type Role = S["RoleEnum"];
export type Paginated<T> = {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
};

const org = (id: string) => `/organisations/${id}`;

export const orgApi = {
  create: (data: OrganisationCreate) => api.post<Organisation>("/organisations/", data),
  get: (id: string) => api.get<Organisation>(`${org(id)}/`),
  update: (id: string, data: OrganisationPatch) => api.patch<Organisation>(`${org(id)}/`, data),
  uploadLogo: (id: string, file: File) => {
    const form = new FormData();
    form.append("logo", file);
    return api.post<Organisation>(`${org(id)}/logo/`, form);
  },
  policy: (id: string) => api.get<Policy>(`${org(id)}/policies/`),
  updatePolicy: (id: string, data: PolicyPatch) => api.patch<Policy>(`${org(id)}/policies/`, data),

  departments: (id: string) =>
    api.get<Paginated<Department>>(`${org(id)}/departments/`, { query: { page_size: 100 } }),
  createDepartment: (id: string, name: string) =>
    api.post<Department>(`${org(id)}/departments/`, { name }),
  updateDepartment: (id: string, depId: string, name: string) =>
    api.patch<Department>(`${org(id)}/departments/${depId}/`, { name }),
  deleteDepartment: (id: string, depId: string) =>
    api.delete<void>(`${org(id)}/departments/${depId}/`),

  locations: (id: string) =>
    api.get<Paginated<Location>>(`${org(id)}/locations/`, { query: { page_size: 100 } }),
  createLocation: (id: string, data: Pick<Location, "name" | "city" | "workplace_type_default">) =>
    api.post<Location>(`${org(id)}/locations/`, data),
  deleteLocation: (id: string, locId: string) => api.delete<void>(`${org(id)}/locations/${locId}/`),

  members: (id: string) =>
    api.get<Paginated<Membership>>(`${org(id)}/members/`, { query: { page_size: 100 } }),
  changeRole: (id: string, membershipId: string, role: Role, reason?: string) =>
    api.patch<Membership>(`${org(id)}/members/${membershipId}/`, { role, reason }),
  deactivate: (id: string, membershipId: string, reason: string) =>
    apiRequest<{ membership: Membership; sessions_revoked: number; needs_reassignment: unknown[] }>(
      `${org(id)}/members/${membershipId}/`,
      { method: "DELETE", body: { reason } },
    ),

  invitations: (id: string, pendingOnly = true) =>
    api.get<Paginated<Invitation>>(`${org(id)}/invitations/`, {
      query: { status: pendingOnly ? "pending" : undefined, page_size: 100 },
    }),
  invite: (id: string, data: InvitationCreate) =>
    api.post<Invitation>(`${org(id)}/invitations/`, data),
  resendInvitation: (id: string, invId: string) =>
    api.post<Invitation>(`${org(id)}/invitations/${invId}/resend/`),
  revokeInvitation: (id: string, invId: string) =>
    api.delete<Invitation>(`${org(id)}/invitations/${invId}/`),

  previewInvitation: (token: string) =>
    api.get<InvitationPublic>(`/invitations/${encodeURIComponent(token)}/`),
  acceptInvitation: (token: string) =>
    api.post<Membership>(`/invitations/${encodeURIComponent(token)}/accept/`),
  setActiveOrg: (organisationId: string) =>
    api.post<{ organisation_id: string; role: string }>("/me/active-org/", {
      organisation_id: organisationId,
    }),
};
