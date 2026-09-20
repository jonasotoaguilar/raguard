import {
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { ApiError, adminAllowed } from '../api/client'
import {
  listMemberships,
  listRoles,
  listUsers,
  MEMBERSHIPS_QUERY_KEY,
  type MembershipsResponse,
  type OrgRole,
  ROLES_QUERY_KEY,
  type RolesResponse,
  USERS_QUERY_KEY,
  updateMembership,
  updateRole,
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

/** Backend capability allowlist, exactly as enforced by the org API. */
export const ALLOWED_CAPABILITIES = [
  'org.settings.manage',
  'users.manage',
  'documents.manage',
  'corpus.view',
  'chat.use',
] as const

function asApiError(error: unknown): ApiError | null {
  return error instanceof ApiError ? error : null
}

type MutationFeedback =
  | { kind: 'idle' }
  | { kind: 'success' }
  | { kind: 'forbidden' }
  | { kind: 'error'; message: string }

function mutationErrorFeedback(error: unknown): MutationFeedback {
  const apiError = asApiError(error)
  if (apiError?.status === 403) return { kind: 'forbidden' }
  // Never echo 404 bodies: the target may belong to another tenant.
  if (apiError?.status === 404)
    return {
      kind: 'error',
      message:
        'Could not save changes. The item may have been removed. Refresh to see the latest data.',
    }
  return {
    kind: 'error',
    message: apiError?.message ?? 'Could not save changes. Please try again.',
  }
}

function sameCapabilities(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  const sortedA = [...a].sort()
  const sortedB = [...b].sort()
  return sortedA.every((value, index) => value === sortedB[index])
}

function MutationFeedbackView({ feedback }: { feedback: MutationFeedback }) {
  if (feedback.kind === 'success') return <p role="status">Saved.</p>
  if (feedback.kind === 'forbidden')
    return (
      <div role="alert">
        <ForbiddenState />
      </div>
    )
  if (feedback.kind === 'error') return <p role="alert">{feedback.message}</p>
  return null
}

function RoleEditor({ role }: { role: OrgRole }) {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<string[]>(role.capabilities)
  const [feedback, setFeedback] = useState<MutationFeedback>({ kind: 'idle' })
  const mutation = useMutation({
    mutationFn: (capabilities: string[]) => updateRole(role.id, capabilities),
    onMutate: async (capabilities) => {
      setFeedback({ kind: 'idle' })
      await queryClient.cancelQueries({ queryKey: ROLES_QUERY_KEY })
      const previous = queryClient.getQueryData<RolesResponse>(ROLES_QUERY_KEY)
      const snapshot =
        previous?.roles.find((entry) => entry.id === role.id)?.capabilities ??
        role.capabilities
      queryClient.setQueryData<RolesResponse>(ROLES_QUERY_KEY, (old) =>
        old
          ? {
              roles: old.roles.map((entry) =>
                entry.id === role.id ? { ...entry, capabilities } : entry,
              ),
            }
          : old,
      )
      return { previous, snapshot }
    },
    onError: (error, _variables, context) => {
      if (context?.previous)
        queryClient.setQueryData<RolesResponse>(
          ROLES_QUERY_KEY,
          context.previous,
        )
      setFeedback(mutationErrorFeedback(error))
      if (context) setSelected(context.snapshot)
    },
    onSuccess: (updated) => {
      setSelected(updated.capabilities)
      setFeedback({ kind: 'success' })
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ROLES_QUERY_KEY })
    },
  })

  const dirty = !sameCapabilities(selected, role.capabilities)

  return (
    <form
      aria-label={`Edit capabilities for ${role.name}`}
      onSubmit={(event) => {
        event.preventDefault()
        if (!dirty || mutation.isPending) return
        mutation.mutate(selected)
      }}
    >
      <fieldset>
        <legend>Edit capabilities</legend>
        {ALLOWED_CAPABILITIES.map((capability) => (
          <label key={capability}>
            <input
              type="checkbox"
              checked={selected.includes(capability)}
              disabled={mutation.isPending}
              onChange={(event) => {
                setSelected((current) =>
                  event.target.checked
                    ? [...current, capability]
                    : current.filter((entry) => entry !== capability),
                )
              }}
            />
            {capability}
          </label>
        ))}
      </fieldset>
      <button
        type="submit"
        disabled={!dirty || mutation.isPending}
        aria-busy={mutation.isPending || undefined}
      >
        {mutation.isPending ? 'Saving role…' : 'Save role'}
      </button>
      {mutation.isPending ? <p role="status">Saving role…</p> : null}
      <MutationFeedbackView feedback={feedback} />
    </form>
  )
}

function MembershipEditor({
  membershipId,
  userEmail,
  currentRole,
  roles,
}: {
  membershipId: string
  userEmail: string
  currentRole: string
  roles: OrgRole[]
}) {
  const queryClient = useQueryClient()
  const initialRoleId =
    roles.find((role) => role.name === currentRole)?.id ?? roles[0]?.id ?? ''
  const [selectedRoleId, setSelectedRoleId] = useState(initialRoleId)
  const [feedback, setFeedback] = useState<MutationFeedback>({ kind: 'idle' })
  const mutation = useMutation({
    mutationFn: (roleId: string) => updateMembership(membershipId, roleId),
    onMutate: async (roleId) => {
      setFeedback({ kind: 'idle' })
      await queryClient.cancelQueries({ queryKey: MEMBERSHIPS_QUERY_KEY })
      const previous = queryClient.getQueryData<MembershipsResponse>(
        MEMBERSHIPS_QUERY_KEY,
      )
      const snapshot =
        previous?.memberships.find((entry) => entry.id === membershipId)
          ?.role ?? currentRole
      const roleName = roles.find((role) => role.id === roleId)?.name
      queryClient.setQueryData<MembershipsResponse>(
        MEMBERSHIPS_QUERY_KEY,
        (old) =>
          old
            ? {
                memberships: old.memberships.map((entry) =>
                  entry.id === membershipId
                    ? { ...entry, role: roleName ?? entry.role }
                    : entry,
                ),
              }
            : old,
      )
      return { previous, snapshot }
    },
    onError: (error, _variables, context) => {
      if (context?.previous)
        queryClient.setQueryData<MembershipsResponse>(
          MEMBERSHIPS_QUERY_KEY,
          context.previous,
        )
      setFeedback(mutationErrorFeedback(error))
      if (context)
        setSelectedRoleId(
          roles.find((role) => role.name === context.snapshot)?.id ??
            initialRoleId,
        )
    },
    onSuccess: (updated) => {
      setSelectedRoleId(updated.role_id)
      setFeedback({ kind: 'success' })
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: MEMBERSHIPS_QUERY_KEY })
    },
  })

  if (roles.length === 0) return null
  const dirty = selectedRoleId !== initialRoleId && selectedRoleId !== ''

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (!dirty || mutation.isPending) return
        mutation.mutate(selectedRoleId)
      }}
    >
      <label>
        Role for {userEmail}
        <select
          value={selectedRoleId}
          disabled={mutation.isPending}
          onChange={(event) => setSelectedRoleId(event.target.value)}
        >
          {roles.map((role) => (
            <option key={role.id} value={role.id}>
              {role.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={!dirty || mutation.isPending}
        aria-busy={mutation.isPending || undefined}
      >
        {mutation.isPending ? 'Saving membership…' : 'Save membership'}
      </button>
      {mutation.isPending ? <p role="status">Saving membership…</p> : null}
      <MutationFeedbackView feedback={feedback} />
    </form>
  )
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
 * ODD-5 admin overview with rollback-safe edits. Route `beforeLoad` keeps
 * anonymous users out; `adminAllowed()` is a UX guard only and the API stays
 * authoritative, so any 403 still renders ForbiddenState. Tenant-safe fields
 * only (user email/id, membership user_email/role, role name/capabilities)
 * render as inert text in semantic tables; role IDs and tenant IDs never
 * render. Capability checkboxes follow the backend allowlist exactly, the
 * membership role select is built from GET /api/org/roles, and every edit is
 * an optimistic TanStack Query mutation with snapshot rollback on error and
 * refetch on settle — the cache never overrides the server.
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
                <th scope="col">Edit role</th>
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
                  <td>
                    <MembershipEditor
                      membershipId={membership.id}
                      userEmail={membership.user_email}
                      currentRole={membership.role}
                      roles={roleList}
                    />
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
                <th scope="col">Edit capabilities</th>
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
                  <td>
                    <RoleEditor role={role} />
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
