import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Citation } from '../api/chat'
import { SourcePreview } from './SourcePreview'

afterEach(() => {
  cleanup()
})

const CITATIONS: Citation[] = [
  {
    chunk_id: '11111111-1111-1111-1111-111111111111',
    document_id: '22222222-2222-2222-2222-222222222222',
    document_name: 'alpha-guide.pdf',
    position: 0,
    content: 'alpha beta gamma passage',
  },
  {
    chunk_id: '33333333-3333-3333-3333-333333333333',
    document_id: '44444444-4444-4444-4444-444444444444',
    document_name: 'beta-notes.md',
    position: 3,
    content: 'beta delta epsilon passage',
  },
]

function renderPreview(
  overrides: Partial<Parameters<typeof SourcePreview>[0]> = {},
) {
  const onClose = vi.fn()
  const onPrevious = vi.fn()
  const onNext = vi.fn()
  const utils = render(
    <SourcePreview
      citation={CITATIONS[0]}
      citations={CITATIONS}
      selectedIndex={0}
      onClose={onClose}
      onPrevious={onPrevious}
      onNext={onNext}
      {...overrides}
    />,
  )
  return { onClose, onPrevious, onNext, ...utils }
}

describe('SourcePreview', () => {
  it('opens as a labelled modal dialog with passage and chunk context', () => {
    renderPreview()
    const dialog = screen.getByRole('dialog', { name: /alpha-guide\.pdf/i })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(
      screen.getByRole('heading', { name: /alpha-guide\.pdf/i }),
    ).toBeVisible()
    expect(screen.getByText(/position 0/i)).toBeVisible()
    expect(screen.getByText('alpha beta gamma passage')).toBeVisible()
    expect(screen.getByText(/chunk 1 of 2/i)).toBeVisible()
  })

  it('renders source text as inert text without links or markup', () => {
    const evil: Citation = {
      ...CITATIONS[0],
      content: '<script>alert(1)</script><a href="https://evil.test">click</a>',
    }
    const { container } = renderPreview({ citation: evil, citations: [evil] })
    expect(
      screen.getByText(
        '<script>alert(1)</script><a href="https://evil.test">click</a>',
      ),
    ).toBeVisible()
    expect(container.querySelector('a')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
  })

  it('moves focus into the dialog close button on open', () => {
    renderPreview()
    expect(screen.getByRole('button', { name: /close/i })).toHaveFocus()
  })

  it('closes on Escape', async () => {
    const user = userEvent.setup()
    const { onClose } = renderPreview()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes on Escape after focus has moved outside the dialog', async () => {
    const user = userEvent.setup()
    const { onClose } = renderPreview()
    const outside = document.createElement('button')
    outside.textContent = 'outside trigger'
    document.body.appendChild(outside)
    outside.focus()
    expect(outside).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
    outside.remove()
  })

  it('traps Tab forward and Shift+Tab backward within dialog controls', async () => {
    const user = userEvent.setup()
    // Index 0 of 2: Previous disabled, so the trap cycles Close <-> Next.
    renderPreview()
    const close = screen.getByRole('button', { name: /close/i })
    const next = screen.getByRole('button', { name: /next/i })
    expect(close).toHaveFocus()
    await user.tab()
    expect(next).toHaveFocus()
    await user.tab()
    expect(close).toHaveFocus()
    await user.tab({ shift: true })
    expect(next).toHaveFocus()
    await user.tab({ shift: true })
    expect(close).toHaveFocus()
  })

  it('calls onClose from the close button and restores focus to the marker trigger', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    const { rerender } = render(<button type="button">marker trigger</button>)
    const trigger = screen.getByRole('button', { name: /marker trigger/i })
    trigger.focus()
    expect(trigger).toHaveFocus()
    rerender(
      <>
        <button type="button">marker trigger</button>
        <SourcePreview
          citation={CITATIONS[0]}
          citations={CITATIONS}
          selectedIndex={0}
          onClose={onClose}
          onPrevious={vi.fn()}
          onNext={vi.fn()}
        />
      </>,
    )
    expect(screen.getByRole('button', { name: /close/i })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
    rerender(<button type="button">marker trigger</button>)
    expect(
      screen.getByRole('button', { name: /marker trigger/i }),
    ).toHaveFocus()
  })

  it('shows a neutral missing card without cached content for null citation', () => {
    const { rerender } = renderPreview()
    expect(screen.getByText('alpha beta gamma passage')).toBeVisible()
    rerender(
      <SourcePreview
        citation={null}
        citations={CITATIONS}
        selectedIndex={0}
        onClose={vi.fn()}
        onPrevious={vi.fn()}
        onNext={vi.fn()}
      />,
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeVisible()
    expect(
      screen.getByText(
        "This source isn't available or you don't have access to it.",
      ),
    ).toBeVisible()
    expect(screen.queryByText('alpha beta gamma passage')).toBeNull()
    expect(screen.queryByText('beta delta epsilon passage')).toBeNull()
  })

  it('bounds Previous/Next to the returned citations and wires callbacks', async () => {
    const user = userEvent.setup()
    const first = renderPreview({ selectedIndex: 0 })
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /next/i })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: /next/i }))
    expect(first.onNext).toHaveBeenCalledTimes(1)
    expect(first.onPrevious).not.toHaveBeenCalled()
    first.unmount()

    const last = renderPreview({ citation: CITATIONS[1], selectedIndex: 1 })
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled()
    expect(screen.getByText(/chunk 2 of 2/i)).toBeVisible()
    await user.click(screen.getByRole('button', { name: /previous/i }))
    expect(last.onPrevious).toHaveBeenCalledTimes(1)
    expect(last.onNext).not.toHaveBeenCalled()
    last.unmount()
  })
})
