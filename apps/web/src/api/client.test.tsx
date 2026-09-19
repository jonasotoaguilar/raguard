import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  adminAllowed,
  apiFetch,
  authGuardRedirect,
  clearSession,
  isAuthenticated,
  login,
  loginRedirect,
  setSession,
  setUnauthorizedHandler,
  toApiError,
} from './client'

function jsonResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  })
}

beforeEach(() => {
  vi.unstubAllGlobals()
  clearSession()
  setUnauthorizedHandler(null)
})

describe('login', () => {
  it('POSTs credentials with cookies and marks the session', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { message: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)
    await login('Member@Example.com', 's3cret')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/login',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      email: 'Member@Example.com',
      password: 's3cret',
    })
    expect(isAuthenticated()).toBe(true)
  })

  it('maps a 401 envelope without firing the router redirect', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(401, {
          error: {
            code: 'authentication_failed',
            message: 'Invalid email or password',
          },
        }),
      ),
    )
    await expect(login('a@b.c', 'wrong')).rejects.toMatchObject({
      code: 'authentication_failed',
      status: 401,
    })
    expect(onUnauthorized).not.toHaveBeenCalled()
    expect(isAuthenticated()).toBe(false)
  })
})

describe('apiFetch guards', () => {
  it('notifies the router on 401 with the return path', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    setSession({ authenticated: true })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(401, {
          error: { code: 'authentication_failed', message: 'Expired' },
        }),
      ),
    )
    await expect(apiFetch('/api/documents')).rejects.toMatchObject({
      status: 401,
    })
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('maps 403 without redirecting', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(403, { error: { code: 'forbidden', message: 'Nope' } }),
        ),
    )
    await expect(apiFetch('/api/admin')).rejects.toMatchObject({
      code: 'forbidden',
      status: 403,
    })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('exposes Retry-After on 429', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            429,
            { error: { code: 'rate_limited', message: 'Slow down' } },
            { 'retry-after': '30' },
          ),
        ),
    )
    const failure = await apiFetch('/api/chat').catch((error) => error)
    expect(failure.retryAfter).toBe(30)
  })

  it('falls back neutrally on garbage bodies', () => {
    const error = toApiError(500, '<html>oops</html>')
    expect(error.code).toBe('internal_error')
    expect(error.message).toMatch(/try again/i)
  })
})

describe('redirects and roles', () => {
  it('builds /login with an encoded return path', () => {
    expect(loginRedirect('/chat')).toBe('/login?redirect=%2Fchat')
    expect(loginRedirect('https://evil.example/')).toBe(
      '/login?redirect=%2Fchat',
    )
    expect(loginRedirect('//evil.example/')).toBe('/login?redirect=%2Fchat')
  })

  it('guards anonymous paths and lets sessions through', () => {
    expect(authGuardRedirect('/documents')).toBe('/login?redirect=%2Fdocuments')
    setSession({ authenticated: true })
    expect(authGuardRedirect('/documents')).toBeNull()
  })

  it('allows admin routes only for admin sessions', () => {
    expect(adminAllowed()).toBe(false)
    setSession({ authenticated: true, role: 'member' })
    expect(adminAllowed()).toBe(false)
    setSession({ authenticated: true, role: 'admin' })
    expect(adminAllowed()).toBe(true)
  })
})
