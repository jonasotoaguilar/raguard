import { createRoute, redirect, useNavigate } from '@tanstack/react-router'
import { type FormEvent, useState } from 'react'
import { ApiError, isAuthenticated, login } from '../api/client'
import { Button, ErrorState, Input } from '../app/shell'
import { RootRoute } from './__root'

export const loginRoute = createRoute({
  getParentRoute: () => RootRoute,
  path: '/login',
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === 'string' ? search.redirect : '/chat',
  }),
  beforeLoad: () => {
    if (isAuthenticated()) throw redirect({ to: '/chat' })
  },
  component: LoginPage,
})

export function LoginPage() {
  const navigate = useNavigate({ from: loginRoute.id })
  const search = loginRoute.useSearch()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await login(email.trim(), password)
      await navigate({ to: search.redirect as '/chat' })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err
          : new ApiError({
              status: 0,
              code: 'network_error',
              message: 'Network unavailable. Please try again.',
            }),
      )
    } finally {
      setPending(false)
    }
  }

  return (
    <section aria-labelledby="login-title">
      <h1 id="login-title">Sign in</h1>
      {error ? <ErrorState code={error.code} message={error.message} /> : null}
      <form onSubmit={onSubmit}>
        <Input
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          id="password"
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" loading={pending}>
          Sign in
        </Button>
      </form>
    </section>
  )
}
