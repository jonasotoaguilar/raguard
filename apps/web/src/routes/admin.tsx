import { queryOptions, useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ApiError, adminAllowed } from '../api/client'
import {
  listMemberships,
  listRoles,
  listUsers,
  MEMBERSHIPS_QUERY_KEY,
  ROLES_QUERY_KEY,
  USERS_QUERY_KEY,
} from '../api/org'
import { EmptyState, ErrorState, ForbiddenState, Skeleton } from '../app/shell'

/** Stable users listing: sole cache address for the admin users table. */
export function adminUsersQueryOptions() {
  return queryOptions({
    queryKey: USERS_QUERY_KEY,
    queryFn: ({ signal }) => listUsers({ signal }),
  })
}

/** Stable roles listing: sole cache address for the admin roles table. */
export function adminRolesQueryOptions() {
  return queryOptions({
    queryKey: ROLES_QUERY_KEY,
    queryFn: ({ signal }) => listRoles({ signal }),
  })
}

/** Stable memberships listing: sole cache address for the memberships table. */
export function adminMembershipsQueryOptions() {
  return queryOptions({
    queryKey: MEMBERSHIPS_QUERY_KEY,
    queryFn: ({ signal }) => listMemberships({ signal }),
  })
}

function asApiError(error: unknown): ApiError | null {
  return error instanceof ApiError ? error : null
}

function AdminFrame({ children }: { children: ReactNode }) {
  return (
    <section
      aria-labelledby="admin-title"
      style={{ maxWidth: 720, padding: 16 }}
    >
      <h1 id="admin-title">Admin</h1>
      {children}
    </section>
  )
}

/**
 * ODD-5 admin overview (read-only slice). Route `beforeLoad` keeps anonymous
 * users out; `adminAllowed()` is a UX guard only and the API stays
 * authoritative, so any 403 still renders ForbiddenState. Tenant-safe fields
 * only (user email/id, membership user_email/role, role name/capabilities)
 * render as inert text in semantic tables. No edits here; the next slice
 * adds rollback-safe role/membership edits.
 */
export function AdminPage() {
  const allowed = adminAllowed()
  const users = useQuery({ ...adminUsersQueryOptions(), enabled: allowed })
  const memberships = useQuery({
    ...adminMembershipsQueryOptions(),
    enabled: allowed,
  })
  const roles = useQuery({ ...adminRolesQueryOptions(), enabled: allowed })

  if (!allowed) return <ForbiddenState />

  const errors = [users.error, memberships.error, roles.error].map(asApiError)
  if (errors.some((error) => error?.status === 403)) return <ForbiddenState />

  if (users.isPending || memberships.isPending || roles.isPending)
    return (
      <AdminFrame>
        <Skeleton label="Loading admin overview" />
      </AdminFrame>
    )

  const failure = errors.find((error) => error !== null)
  if (users.isError || memberships.isError || roles.isError)
    return (
      <AdminFrame>
        <ErrorState
          code={failure?.code ?? 'unknown_error'}
          message={failure?.message ?? 'Request failed. Please try again.'}
          onRetry={() => {
            void users.refetch()
            void memberships.refetch()
            void roles.refetch()
          }}
        />
      </AdminFrame>
    )

  const userList = users.data?.users ?? []
  const membershipList = memberships.data?.memberships ?? []
  const roleList = roles.data?.roles ?? []

  return (
    <AdminFrame>
      <section aria-labelledby="admin-users-title">
        <h2 id="admin-users-title">Users</h2>
        {userList.length === 0 ? (
          <EmptyState title="No users yet" body="No tenant users to show." />
        ) : (
          <table style={{ width: '100%', marginTop: 8 }}>
            <thead>
              <tr>
                <th scope="col">Email</th>
                <th scope="col">ID</th>
              </tr>
            </thead>
            <tbody>
              {userList.map((user) => (
                <tr key={user.id}>
                  <td style={{ overflowWrap: 'anywhere' }}>{user.email}</td>
                  <td style={{ overflowWrap: 'anywhere' }}>{user.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="admin-memberships-title">
        <h2 id="admin-memberships-title">Memberships</h2>
        {membershipList.length === 0 ? (
          <EmptyState
            title="No memberships yet"
            body="No tenant memberships to show."
          />
        ) : (
          <table style={{ width: '100%', marginTop: 8 }}>
            <thead>
              <tr>
                <th scope="col">User</th>
                <th scope="col">Role</th>
              </tr>
            </thead>
            <tbody>
              {membershipList.map((membership) => (
                <tr key={membership.id}>
                  <td style={{ overflowWrap: 'anywhere' }}>
                    {membership.user_email}
                  </td>
                  <td style={{ overflowWrap: 'anywhere' }}>
                    {membership.role}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="admin-roles-title">
        <h2 id="admin-roles-title">Roles</h2>
        {roleList.length === 0 ? (
          <EmptyState title="No roles yet" body="No tenant roles to show." />
        ) : (
          <table style={{ width: '100%', marginTop: 8 }}>
            <thead>
              <tr>
                <th scope="col">Role</th>
                <th scope="col">Capabilities</th>
              </tr>
            </thead>
            <tbody>
              {roleList.map((role) => (
                <tr key={role.id}>
                  <td style={{ overflowWrap: 'anywhere' }}>{role.name}</td>
                  <td style={{ overflowWrap: 'anywhere' }}>
                    {role.capabilities.length > 0
                      ? role.capabilities.join(', ')
                      : 'No capabilities'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </AdminFrame>
  )
}
