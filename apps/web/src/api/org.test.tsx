import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  listMemberships,
  listRoles,
  listUsers,
  MEMBERSHIPS_QUERY_KEY,
  ROLES_QUERY_KEY,
  USERS_QUERY_KEY,
  updateMembership,
  updateRole,
} from './org'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

/** Stub fetch with one JSON response; returns the mock for assertions. */
function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(status, body))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  vi.unstubAllGlobals()
})

describe('query keys', () => {
  it('exposes stable keys for users, roles, and memberships', () => {
    expect(USERS_QUERY_KEY).toEqual(['users'])
    expect(ROLES_QUERY_KEY).toEqual(['roles'])
    expect(MEMBERSHIPS_QUERY_KEY).toEqual(['memberships'])
  })
})

describe('listUsers', () => {
  it('GETs /api/org/users and mirrors the users envelope', async () => {
    const user = {
      id: '11111111-1111-1111-1111-111111111111',
      email: 'a@example.com',
    }
    const fetchMock = stubFetch(200, { users: [user] })

    const result = await listUsers()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/org/users',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(fetchMock.mock.calls[0][1].method ?? 'GET').toBe('GET')
    expect(result.users).toEqual([user])
  })

  it('forwards an abort signal', async () => {
    const controller = new AbortController()
    const fetchMock = stubFetch(200, { users: [] })
    await listUsers({ signal: controller.signal })
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('propagates a 403 ApiError with details', async () => {
    stubFetch(403, {
      error: { code: 'forbidden', message: 'Nope', details: { a: 1 } },
    })
    await expect(listUsers()).rejects.toMatchObject({
      status: 403,
      code: 'forbidden',
      message: 'Nope',
      details: { a: 1 },
    })
  })
})

describe('listRoles', () => {
  it('GETs /api/org/roles and mirrors the roles envelope', async () => {
    const role = { id: 'r-1', name: 'admin', capabilities: ['users.manage'] }
    const fetchMock = stubFetch(200, { roles: [role] })

    const result = await listRoles()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/org/roles',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(result.roles).toEqual([role])
  })

  it('forwards an abort signal', async () => {
    const controller = new AbortController()
    const fetchMock = stubFetch(200, { roles: [] })
    await listRoles({ signal: controller.signal })
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('propagates a 403 ApiError', async () => {
    stubFetch(403, { error: { code: 'forbidden', message: 'Nope' } })
    await expect(listRoles()).rejects.toMatchObject({
      status: 403,
      code: 'forbidden',
    })
  })
})

describe('listMemberships', () => {
  it('GETs /api/org/memberships and mirrors the memberships envelope', async () => {
    const membership = { id: 'm-1', user_email: 'a@example.com', role: 'admin' }
    const fetchMock = stubFetch(200, { memberships: [membership] })

    const result = await listMemberships()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/org/memberships',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(result.memberships).toEqual([membership])
  })

  it('forwards an abort signal', async () => {
    const controller = new AbortController()
    const fetchMock = stubFetch(200, { memberships: [] })
    await listMemberships({ signal: controller.signal })
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('propagates a 403 ApiError', async () => {
    stubFetch(403, { error: { code: 'forbidden', message: 'Nope' } })
    await expect(listMemberships()).rejects.toMatchObject({
      status: 403,
      code: 'forbidden',
    })
  })
})

describe('updateRole', () => {
  const updated = {
    id: 'r-1',
    name: 'member',
    capabilities: ['chat.use', 'users.manage'],
  }

  it('PATCHes /api/org/roles/{id} with capabilities and mirrors the role', async () => {
    const fetchMock = stubFetch(200, updated)

    const result = await updateRole('r-1', ['chat.use', 'users.manage'])

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/org/roles/r-1',
      expect.objectContaining({ method: 'PATCH', credentials: 'include' }),
    )
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      capabilities: ['chat.use', 'users.manage'],
    })
    expect(result).toEqual(updated)
  })

  it('forwards an abort signal', async () => {
    const controller = new AbortController()
    const fetchMock = stubFetch(200, updated)
    await updateRole('r-1', ['chat.use'], { signal: controller.signal })
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('propagates a 400 validation error', async () => {
    stubFetch(400, {
      error: { code: 'invalid_request', message: 'Unknown capabilities' },
    })
    await expect(
      updateRole('r-1', ['delete.everything']),
    ).rejects.toMatchObject({
      status: 400,
      code: 'invalid_request',
    })
  })

  it('propagates a 404 for an unknown role', async () => {
    stubFetch(404, { error: { code: 'not_found', message: 'Role not found' } })
    await expect(updateRole('missing', ['chat.use'])).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
    })
  })
})

describe('updateMembership', () => {
  const updated = { id: 'm-1', role_id: 'r-1' }

  it('PATCHes /api/org/memberships/{id} with role_id and mirrors the membership', async () => {
    const fetchMock = stubFetch(200, updated)

    const result = await updateMembership('m-1', 'r-1')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/org/memberships/m-1',
      expect.objectContaining({ method: 'PATCH', credentials: 'include' }),
    )
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      role_id: 'r-1',
    })
    expect(result).toEqual(updated)
  })

  it('forwards an abort signal', async () => {
    const controller = new AbortController()
    const fetchMock = stubFetch(200, updated)
    await updateMembership('m-1', 'r-1', { signal: controller.signal })
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('propagates a 404 for an unknown membership', async () => {
    stubFetch(404, {
      error: { code: 'not_found', message: 'Membership not found' },
    })
    await expect(updateMembership('missing', 'r-1')).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
    })
  })
})
