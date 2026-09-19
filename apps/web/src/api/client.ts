/** ODD-1 API client: envelope mapping, 401/403/429 handling, session, login. */

export interface ApiErrorInit {
  status: number
  code: string
  message: string
  details?: unknown
}

export class ApiError extends Error {
  status: number
  code: string
  details?: unknown
  retryAfter: number | null = null
  constructor(init: ApiErrorInit) {
    super(init.message)
    this.name = 'ApiError'
    this.status = init.status
    this.code = init.code
    this.details = init.details
  }
}

const FALLBACK_CODES: Record<number, string> = {
  400: 'invalid_request',
  401: 'authentication_failed',
  403: 'forbidden',
  404: 'not_found',
  409: 'conflict',
  429: 'rate_limited',
}

/** Map `{error: {code, message, details?}}` (or garbage) to an ApiError. */
export function toApiError(status: number, body: unknown): ApiError {
  const envelope = (body as { error?: Record<string, unknown> } | null)?.error
  const code =
    typeof envelope?.code === 'string' && envelope.code
      ? envelope.code
      : (FALLBACK_CODES[status] ??
        (status >= 500 ? 'internal_error' : 'unknown_error'))
  const message =
    typeof envelope?.message === 'string' && envelope.message
      ? envelope.message
      : 'Request failed. Please try again.'
  return new ApiError({ status, code, message, details: envelope?.details })
}

/** Seconds from a `Retry-After` header; null when absent/unparseable. */
export function parseRetryAfter(value: string | null): number | null {
  if (value === null) return null
  const seconds = Number.parseInt(value.trim(), 10)
  return Number.isSafeInteger(seconds) && seconds >= 0 ? seconds : null
}

export const LOGIN_API_PATH = '/api/auth/login'

type UnauthorizedHandler = (returnPath: string) => void
let unauthorizedHandler: UnauthorizedHandler | null = null

/** Router registers this so background 401s redirect to /login with context. */
export function setUnauthorizedHandler(
  handler: UnauthorizedHandler | null,
): void {
  unauthorizedHandler = handler
}

export function currentPath(): string {
  return typeof window === 'undefined'
    ? '/chat'
    : `${window.location.pathname}${window.location.search}`
}

/** `/login?redirect=…`; external/protocol-relative targets fall back to /chat. */
export function loginRedirect(returnPath: string): string {
  const safe =
    returnPath.startsWith('/') && !returnPath.startsWith('//')
      ? returnPath
      : '/chat'
  return `/login?redirect=${encodeURIComponent(safe)}`
}

export interface Session {
  authenticated: boolean
  role?: string
}
let session: Session = { authenticated: false }

export function setSession(next: Session): void {
  session = { ...next }
}
export function getSession(): Session {
  return { ...session }
}
export function clearSession(): void {
  session = { authenticated: false }
}
export function isAuthenticated(): boolean {
  return session.authenticated
}

/** Route-guard helper: redirect target when anonymous, null when allowed. */
export function authGuardRedirect(path: string): string | null {
  return isAuthenticated() ? null : loginRedirect(path)
}

/** Admin-guard helper: true only for an authenticated admin session. */
export function adminAllowed(): boolean {
  return session.authenticated && session.role === 'admin'
}

/** Same-domain JSON fetch with envelope errors; 401s notify the router. */
export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...((init.headers as Record<string, string>) ?? {}),
  }
  if (init.body !== undefined && headers['content-type'] === undefined)
    headers['content-type'] = 'application/json'
  const res = await fetch(path, { ...init, headers, credentials: 'include' })
  if (res.status === 204) return undefined as T
  const isJson =
    res.headers.get('content-type')?.includes('application/json') ?? false
  const body: unknown = isJson
    ? await res.json().catch(() => undefined)
    : await res.text().catch(() => undefined)
  if (res.ok) return (body ?? {}) as T
  const error = toApiError(res.status, body)
  if (res.status === 429)
    error.retryAfter = parseRetryAfter(res.headers.get('retry-after'))
  if (res.status === 401 && path !== LOGIN_API_PATH)
    unauthorizedHandler?.(currentPath())
  throw error
}

/** POST /api/auth/login (HttpOnly cookie set by the API); marks session. */
export async function login(email: string, password: string): Promise<void> {
  await apiFetch<{ message: string }>(LOGIN_API_PATH, {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  setSession({ authenticated: true })
}

/** Sign out client-side: drop session so guards redirect to /login. */
export function logout(): void {
  clearSession()
}
