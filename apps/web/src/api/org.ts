/** ODD-5 org/admin API: tenant-scoped users, roles, and memberships. */
import { apiFetch } from './client'

export interface OrgUser {
  id: string
  email: string
}

export interface OrgRole {
  id: string
  name: string
  capabilities: string[]
}

export interface OrgMembership {
  id: string
  user_email: string
  role: string
}

export interface UsersResponse {
  users: OrgUser[]
}

export interface RolesResponse {
  roles: OrgRole[]
}

export interface MembershipsResponse {
  memberships: OrgMembership[]
}

export interface UpdatedMembership {
  id: string
  role_id: string
}

export const ORG_API_PATH = '/api/org'

export const USERS_QUERY_KEY = ['users'] as const
export const ROLES_QUERY_KEY = ['roles'] as const
export const MEMBERSHIPS_QUERY_KEY = ['memberships'] as const

/** GET /api/org/users: tenant-scoped list; backend returns `{users: [...]}`. */
export function listUsers(
  init: { signal?: AbortSignal } = {},
): Promise<UsersResponse> {
  return apiFetch<UsersResponse>(`${ORG_API_PATH}/users`, {
    signal: init.signal,
  })
}

/** GET /api/org/roles: tenant-scoped list; backend returns `{roles: [...]}`. */
export function listRoles(
  init: { signal?: AbortSignal } = {},
): Promise<RolesResponse> {
  return apiFetch<RolesResponse>(`${ORG_API_PATH}/roles`, {
    signal: init.signal,
  })
}

/** GET /api/org/memberships: tenant-scoped list; returns `{memberships: [...]}`. */
export function listMemberships(
  init: { signal?: AbortSignal } = {},
): Promise<MembershipsResponse> {
  return apiFetch<MembershipsResponse>(`${ORG_API_PATH}/memberships`, {
    signal: init.signal,
  })
}

/** PATCH /api/org/roles/{role_id}: replace capabilities; mirrors the updated role. */
export function updateRole(
  roleId: string,
  capabilities: string[],
  init: { signal?: AbortSignal } = {},
): Promise<OrgRole> {
  return apiFetch<OrgRole>(`${ORG_API_PATH}/roles/${roleId}`, {
    method: 'PATCH',
    body: JSON.stringify({ capabilities }),
    signal: init.signal,
  })
}

/** PATCH /api/org/memberships/{membership_id}: reassign role; mirrors `{id, role_id}`. */
export function updateMembership(
  membershipId: string,
  roleId: string,
  init: { signal?: AbortSignal } = {},
): Promise<UpdatedMembership> {
  return apiFetch<UpdatedMembership>(
    `${ORG_API_PATH}/memberships/${membershipId}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ role_id: roleId }),
      signal: init.signal,
    },
  )
}
