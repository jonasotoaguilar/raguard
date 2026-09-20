import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { StatusChip } from './StatusChip'

afterEach(() => {
  cleanup()
})

describe('StatusChip', () => {
  it.each([
    ['pending', 'Pending', '○'],
    ['indexing', 'Indexing', '◐'],
    ['indexed', 'Indexed', '●'],
    ['failed', 'Failed', '✕'],
  ] as const)(
    'renders the %s state with text and a non-color marker',
    (status, label, icon) => {
      render(<StatusChip status={status} />)
      const chip = screen.getByTestId('status-chip')
      expect(chip.textContent).toContain(label)
      expect(chip.textContent).toContain(icon)
    },
  )

  it('renders the failure reason text for failed documents', () => {
    render(<StatusChip status="failed" failureReason="malformed" />)
    expect(screen.getByTestId('status-chip-reason').textContent).toContain(
      'malformed',
    )
  })

  it('renders no reason element when none is supplied', () => {
    render(<StatusChip status="failed" failureReason={null} />)
    expect(screen.queryByTestId('status-chip-reason')).not.toBeInTheDocument()
  })

  it('renders the reason as inert text, never markup', () => {
    render(<StatusChip status="failed" failureReason="<img src=x>" />)
    expect(screen.getByTestId('status-chip-reason').textContent).toContain(
      '<img src=x>',
    )
    expect(
      screen.getByTestId('status-chip').querySelector('img'),
    ).not.toBeInTheDocument()
  })
})
