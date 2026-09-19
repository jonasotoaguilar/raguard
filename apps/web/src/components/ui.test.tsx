import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import {
  AppShell,
  Button,
  EmptyState,
  ErrorState,
  ForbiddenState,
  Input,
  Skeleton,
} from '../app/shell'

describe('primitives', () => {
  it('renders a loading button as busy and disabled', () => {
    render(<Button loading>Sign in</Button>)
    const button = screen.getByRole('button', { name: /loading/i })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })

  it('labels inputs and describes errors', () => {
    render(<Input id="email" label="Email" error="Required" />)
    expect(screen.getByLabelText('Email')).toHaveAttribute(
      'aria-describedby',
      'email-error',
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Required')
  })

  it('shows empty and error states with a retry action', () => {
    const onRetry = vi.fn()
    render(<EmptyState title="No documents" body="Upload one to begin." />)
    expect(screen.getByText('No documents')).toBeInTheDocument()
    render(
      <ErrorState
        code="service_unavailable"
        message="Answer engine down."
        onRetry={onRetry}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/service_unavailable/)).toBeInTheDocument()
  })

  it('keeps the forbidden surface neutral', () => {
    render(<ForbiddenState />)
    expect(screen.getByText(/not available/i)).toBeInTheDocument()
    expect(screen.queryByText(/does not exist/i)).not.toBeInTheDocument()
  })

  it('renders a skeleton status', () => {
    render(<Skeleton />)
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument()
  })
})

describe('AppShell', () => {
  it('shows the tenant, a skip link, and at most five links', () => {
    const nav = Array.from({ length: 7 }, (_, i) => ({
      to: `/p${i}`,
      label: `P${i}`,
    }))
    render(
      <AppShell tenantName="acme" nav={nav}>
        <p>child</p>
      </AppShell>,
    )
    expect(screen.getByLabelText('Active tenant')).toHaveTextContent('acme')
    expect(
      screen.getByRole('link', { name: /skip to content/i }),
    ).toHaveAttribute('href', '#main')
    expect(
      screen
        .getByRole('navigation', { name: /primary/i })
        .querySelectorAll('a'),
    ).toHaveLength(5)
    expect(screen.getByRole('main')).toHaveTextContent('child')
  })
})
