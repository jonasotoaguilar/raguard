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
}))

const usersMock = vi.mocked(listUsers)
const rolesMock = vi.mocked(listRoles)
const membershipsMock = vi.mocked(listMemberships)

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
    expect(screen.getByText('users.manage')).toBeInTheDocument()
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

it('uses the stable org query keys', () => {
  expect(adminUsersQueryOptions().queryKey).toEqual([...USERS_QUERY_KEY])
  expect(adminRolesQueryOptions().queryKey).toEqual([...ROLES_QUERY_KEY])
  expect(adminMembershipsQueryOptions().queryKey).toEqual([
    ...MEMBERSHIPS_QUERY_KEY,
  ])
})
