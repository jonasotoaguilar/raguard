import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, clearSession, setSession } from '../api/client'
import {
  listMemberships,
  listRoles,
  listUsers,
  MEMBERSHIPS_QUERY_KEY,
  ROLES_QUERY_KEY,
  USERS_QUERY_KEY,
  updateMembership,
  updateRole,
} from '../api/org'
import {
  AdminPage,
  adminMembershipsQueryOptions,
  adminRolesQueryOptions,
  adminUsersQueryOptions,
} from './admin'

vi.mock('../api/org', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/org')>()),
  listUsers: vi.fn(),
  listRoles: vi.fn(),
  listMemberships: vi.fn(),
  updateRole: vi.fn(),
  updateMembership: vi.fn(),
}))

const usersMock = vi.mocked(listUsers)
const rolesMock = vi.mocked(listRoles)
const membershipsMock = vi.mocked(listMemberships)
const updateRoleMock = vi.mocked(updateRole)
const updateMembershipMock = vi.mocked(updateMembership)

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <AdminPage />
    </QueryClientProvider>,
  )
}

function seedSuccess() {
  usersMock.mockResolvedValue({
    users: [{ id: 'u-1', email: 'a@example.com' }],
  })
  membershipsMock.mockResolvedValue({
    memberships: [{ id: 'm-1', user_email: 'a@example.com', role: 'admin' }],
  })
  rolesMock.mockResolvedValue({
    roles: [{ id: 'r-1', name: 'admin', capabilities: ['users.manage'] }],
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  setSession({ authenticated: true, role: 'admin' })
})

afterEach(() => {
  cleanup()
  clearSession()
})

describe('AdminPage guard', () => {
  it('renders ForbiddenState for non-admins without fetching', () => {
    setSession({ authenticated: true, role: 'member' })
    renderPage()

    expect(screen.getByLabelText(/forbidden/i)).toBeInTheDocument()
    expect(usersMock).not.toHaveBeenCalled()
    expect(rolesMock).not.toHaveBeenCalled()
    expect(membershipsMock).not.toHaveBeenCalled()
  })
})

describe('AdminPage tables', () => {
  it('renders the heading, scoped headers, and tenant-safe fields', async () => {
    seedSuccess()
    renderPage()

    expect(screen.getByRole('heading', { name: /admin/i })).toBeInTheDocument()
    // The seed email appears in both the users and memberships tables.
    await waitFor(() =>
      expect(screen.getAllByText('a@example.com')).toHaveLength(2),
    )

    const headers = screen.getAllByRole('columnheader')
    for (const h of headers) expect(h.getAttribute('scope')).toBe('col')
    const labels = headers.map((h) => h.textContent)
    expect(labels).toEqual(
      expect.arrayContaining(['Email', 'ID', 'User', 'Role', 'Capabilities']),
    )
    expect(screen.getByText('u-1')).toBeInTheDocument()
    // The capability renders in the table cell and again as an editor label.
    expect(screen.getAllByText('users.manage').length).toBeGreaterThanOrEqual(1)
  })

  it('renders untrusted API text as inert text without markup', async () => {
    usersMock.mockResolvedValue({
      users: [{ id: 'u-9', email: '<script>alert(1)</script>@x.test' }],
    })
    membershipsMock.mockResolvedValue({ memberships: [] })
    rolesMock.mockResolvedValue({
      roles: [{ id: 'r-9', name: '<b>admin</b>', capabilities: ['<i>x</i>'] }],
    })
    const { container } = renderPage()

    await waitFor(() =>
      expect(
        screen.getByText('<script>alert(1)</script>@x.test'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByText('<b>admin</b>')).toBeInTheDocument()
    expect(screen.getByText('<i>x</i>')).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(container.querySelector('i')).toBeNull()
  })

  it('names empty tables explicitly', async () => {
    usersMock.mockResolvedValue({ users: [] })
    membershipsMock.mockResolvedValue({ memberships: [] })
    rolesMock.mockResolvedValue({ roles: [] })
    renderPage()

    await waitFor(() =>
      expect(screen.getByText(/no users yet/i)).toBeInTheDocument(),
    )
    expect(screen.getByText(/no memberships yet/i)).toBeInTheDocument()
    expect(screen.getByText(/no roles yet/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/error/i)).not.toBeInTheDocument()
  })

  it('shows honest loading state while fetching', () => {
    usersMock.mockReturnValue(new Promise(() => {}) as never)
    rolesMock.mockReturnValue(new Promise(() => {}) as never)
    membershipsMock.mockReturnValue(new Promise(() => {}) as never)
    renderPage()

    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('maps any 403 to ForbiddenState without a retry', async () => {
    usersMock.mockResolvedValue({ users: [] })
    membershipsMock.mockRejectedValue(
      new ApiError({ status: 403, code: 'forbidden', message: 'Nope' }),
    )
    rolesMock.mockResolvedValue({ roles: [] })
    renderPage()

    await waitFor(() =>
      expect(screen.getByLabelText(/forbidden/i)).toBeInTheDocument(),
    )
    expect(
      screen.queryByRole('button', { name: /retry/i }),
    ).not.toBeInTheDocument()
  })

  it('shows a retryable error for 5xx and recovers on retry', async () => {
    usersMock
      .mockRejectedValueOnce(
        new ApiError({ status: 500, code: 'internal_error', message: 'Boom' }),
      )
      .mockResolvedValueOnce({
        users: [{ id: 'u-1', email: 'a@example.com' }],
      })
    membershipsMock.mockResolvedValue({ memberships: [] })
    rolesMock.mockResolvedValue({ roles: [] })
    renderPage()

    await waitFor(() =>
      expect(screen.getByLabelText(/error/i)).toBeInTheDocument(),
    )
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() =>
      expect(screen.getByText('a@example.com')).toBeInTheDocument(),
    )
    expect(usersMock).toHaveBeenCalledTimes(2)
  })
})

describe('AdminPage role edits', () => {
  function seedRoleEdit() {
    usersMock.mockResolvedValue({ users: [] })
    membershipsMock.mockResolvedValue({ memberships: [] })
    rolesMock.mockResolvedValue({
      roles: [{ id: 'r-1', name: 'admin', capabilities: ['users.manage'] }],
    })
  }

  it('saves checked capabilities and invalidates the roles key', async () => {
    seedRoleEdit()
    updateRoleMock.mockResolvedValue({
      id: 'r-1',
      name: 'admin',
      capabilities: ['users.manage', 'chat.use'],
    })
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(screen.getAllByText('users.manage').length).toBeGreaterThanOrEqual(
        1,
      ),
    )
    const callsBefore = rolesMock.mock.calls.length

    await user.click(screen.getByRole('checkbox', { name: 'chat.use' }))
    await user.click(screen.getByRole('button', { name: /save role/i }))

    await waitFor(() =>
      expect(updateRoleMock).toHaveBeenCalledWith('r-1', [
        'users.manage',
        'chat.use',
      ]),
    )
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(/saved/i),
    )
    await waitFor(() =>
      expect(rolesMock.mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('rolls back visibly when saving capabilities fails', async () => {
    seedRoleEdit()
    updateRoleMock.mockRejectedValue(
      new ApiError({ status: 500, code: 'internal_error', message: 'Boom' }),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(screen.getAllByText('users.manage').length).toBeGreaterThanOrEqual(
        1,
      ),
    )

    await user.click(screen.getByRole('checkbox', { name: 'chat.use' }))
    await user.click(screen.getByRole('button', { name: /save role/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    // Optimistic row reverts to the server snapshot.
    await waitFor(() =>
      expect(
        screen.getByRole('checkbox', { name: 'chat.use' }),
      ).not.toBeChecked(),
    )
    expect(screen.queryByText('users.manage, chat.use')).toBeNull()
  })

  it('maps a role-edit 403 to ForbiddenState', async () => {
    seedRoleEdit()
    updateRoleMock.mockRejectedValue(
      new ApiError({ status: 403, code: 'forbidden', message: 'Nope' }),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(screen.getAllByText('users.manage').length).toBeGreaterThanOrEqual(
        1,
      ),
    )

    await user.click(screen.getByRole('checkbox', { name: 'chat.use' }))
    await user.click(screen.getByRole('button', { name: /save role/i }))

    await waitFor(() =>
      expect(screen.getByLabelText(/forbidden/i)).toBeInTheDocument(),
    )
  })

  it('does not leak 404 details for a missing role', async () => {
    seedRoleEdit()
    updateRoleMock.mockRejectedValue(
      new ApiError({
        status: 404,
        code: 'not_found',
        message: 'Role not found super-secret-id',
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(screen.getAllByText('users.manage').length).toBeGreaterThanOrEqual(
        1,
      ),
    )

    await user.click(screen.getByRole('checkbox', { name: 'chat.use' }))
    await user.click(screen.getByRole('button', { name: /save role/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.queryByText(/super-secret-id/)).toBeNull()
  })
})

describe('AdminPage membership edits', () => {
  function seedMembershipEdit() {
    usersMock.mockResolvedValue({ users: [] })
    membershipsMock.mockResolvedValue({
      memberships: [{ id: 'm-1', user_email: 'a@example.com', role: 'admin' }],
    })
    rolesMock.mockResolvedValue({
      roles: [
        { id: 'r-1', name: 'admin', capabilities: ['users.manage'] },
        { id: 'r-2', name: 'member', capabilities: ['chat.use'] },
      ],
    })
  }

  it('reassigns membership role from the roles listing and refetches', async () => {
    seedMembershipEdit()
    updateMembershipMock.mockResolvedValue({ id: 'm-1', role_id: 'r-2' })
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(
        screen.getByLabelText(/role for a@example\.com/i),
      ).toBeInTheDocument(),
    )
    const callsBefore = membershipsMock.mock.calls.length
    // Options come from GET /api/org/roles; no tenant IDs on display.
    expect(screen.getByRole('option', { name: 'member' })).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/r-1/)
    expect(document.body.textContent).not.toMatch(/tenant[-_ ]?id/i)

    await user.selectOptions(
      screen.getByLabelText(/role for a@example\.com/i),
      'r-2',
    )
    await user.click(screen.getByRole('button', { name: /save membership/i }))

    await waitFor(() =>
      expect(updateMembershipMock).toHaveBeenCalledWith('m-1', 'r-2'),
    )
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(/saved/i),
    )
    await waitFor(() =>
      expect(membershipsMock.mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('rolls back visibly when membership reassignment fails', async () => {
    seedMembershipEdit()
    updateMembershipMock.mockRejectedValue(
      new ApiError({ status: 500, code: 'internal_error', message: 'Boom' }),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(
        screen.getByLabelText(/role for a@example\.com/i),
      ).toBeInTheDocument(),
    )

    await user.selectOptions(
      screen.getByLabelText(/role for a@example\.com/i),
      'r-2',
    )
    await user.click(screen.getByRole('button', { name: /save membership/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    await waitFor(() =>
      expect(screen.getByLabelText(/role for a@example\.com/i)).toHaveValue(
        'r-1',
      ),
    )
  })

  it('maps a membership-edit 403 to ForbiddenState', async () => {
    seedMembershipEdit()
    updateMembershipMock.mockRejectedValue(
      new ApiError({ status: 403, code: 'forbidden', message: 'Nope' }),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(
        screen.getByLabelText(/role for a@example\.com/i),
      ).toBeInTheDocument(),
    )

    await user.selectOptions(
      screen.getByLabelText(/role for a@example\.com/i),
      'r-2',
    )
    await user.click(screen.getByRole('button', { name: /save membership/i }))

    await waitFor(() =>
      expect(screen.getByLabelText(/forbidden/i)).toBeInTheDocument(),
    )
  })
})

it('uses the stable org query keys', () => {
  expect(adminUsersQueryOptions().queryKey).toEqual([...USERS_QUERY_KEY])
  expect(adminRolesQueryOptions().queryKey).toEqual([...ROLES_QUERY_KEY])
  expect(adminMembershipsQueryOptions().queryKey).toEqual([
    ...MEMBERSHIPS_QUERY_KEY,
  ])
})
