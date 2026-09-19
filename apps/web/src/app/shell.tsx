import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
} from 'react'

/** Slice-scale tokens from DESIGN.md; components reference these only. */
export const tokens = {
  surface: '#FAF9F5',
  surfaceRaised: '#FFFFFF',
  surfaceMuted: '#F0EDE2',
  ink: '#201D17',
  inkMuted: '#57524A',
  border: '#DCD7C7',
  primary: '#24507E',
  onPrimary: '#FBF9F2',
  danger: '#A63A2B',
  onDanger: '#FFF6F4',
}

type ButtonVariant = 'primary' | 'secondary' | 'destructive' | 'ghost'
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  loading?: boolean
}
const buttonFill: Record<ButtonVariant, [string, string]> = {
  primary: [tokens.primary, tokens.onPrimary],
  secondary: [tokens.surfaceRaised, tokens.ink],
  destructive: [tokens.danger, tokens.onDanger],
  ghost: [tokens.surface, tokens.inkMuted],
}

export function Button({
  variant = 'primary',
  loading = false,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  const [background, color] = buttonFill[variant]
  const style = {
    background,
    color,
    border: `1px solid ${tokens.border}`,
    borderRadius: 8,
    minHeight: 40,
    padding: '0 12px',
  }
  return (
    <button
      type="button"
      disabled={disabled ?? loading}
      aria-busy={loading || undefined}
      style={style}
      {...rest}
    >
      {loading ? 'Loading…' : children}
    </button>
  )
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string
  label: string
  error?: string
}

export function Input({ id, label, error, ...rest }: InputProps) {
  return (
    <div>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        aria-invalid={!!error || undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        style={{
          background: tokens.surfaceRaised,
          color: tokens.ink,
          border: `1px solid ${tokens.border}`,
          borderRadius: 8,
          minHeight: 40,
          padding: '0 12px',
          width: '100%',
        }}
        {...rest}
      />
      {error ? (
        <p id={`${id}-error`} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body?: string
  action?: ReactNode
}) {
  return (
    <section aria-label={title}>
      <h2>{title}</h2>
      {body ? <p>{body}</p> : null}
      {action}
    </section>
  )
}

export function ErrorState({
  code,
  message,
  onRetry,
}: {
  code: string
  message: string
  onRetry?: () => void
}) {
  return (
    <section aria-label="Error" role="alert">
      <h2>Something went wrong</h2>
      <p>
        {message} ({code})
      </p>
      {onRetry ? <Button onClick={onRetry}>Retry</Button> : null}
    </section>
  )
}

/** Neutral 403 surface: identical whether content is missing or hidden. */
export function ForbiddenState() {
  return (
    <section aria-label="Forbidden">
      <h2>Not available</h2>
      <p>
        This content isn&apos;t available or you don&apos;t have access to it.
      </p>
    </section>
  )
}

export function Skeleton({ label = 'Loading' }: { label?: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      style={{
        background: tokens.surfaceMuted,
        borderRadius: 4,
        minHeight: 16,
      }}
    />
  )
}

export interface NavLink {
  to: string
  label: string
}

/** Sidebar nav stays within DESIGN.md's 5-link ceiling. */
export const defaultNav: NavLink[] = [
  { to: '/chat', label: 'Chat' },
  { to: '/documents', label: 'Documents' },
  { to: '/admin', label: 'Admin' },
]

export function AppShell({
  tenantName,
  nav = defaultNav,
  children,
}: {
  tenantName: string
  nav?: NavLink[]
  children: ReactNode
}) {
  return (
    <div style={{ background: tokens.surface, color: tokens.ink }}>
      <a href="#main">Skip to content</a>
      <header>
        <span title="Active tenant">{tenantName}</span>
      </header>
      <nav aria-label="Primary">
        <ul>
          {nav.slice(0, 5).map((l) => (
            <li key={l.to}>
              <a href={l.to}>{l.label}</a>
            </li>
          ))}
        </ul>
      </nav>
      <main id="main" tabIndex={-1}>
        {children}
      </main>
    </div>
  )
}
