import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Citation } from '../api/chat'
import { CitationMarker } from './CitationMarker'

afterEach(() => {
  cleanup()
})

const CITATIONS: Citation[] = [
  {
    chunk_id: '11111111-1111-1111-1111-111111111111',
    document_id: '22222222-2222-2222-2222-222222222222',
    document_name: 'alpha-guide.pdf',
    position: 0,
    content: 'alpha beta gamma',
  },
  {
    chunk_id: '33333333-3333-3333-3333-333333333333',
    document_id: '44444444-4444-4444-4444-444444444444',
    document_name: 'beta-notes.md',
    position: 3,
    content: 'beta delta epsilon',
  },
]

describe('CitationMarker', () => {
  it('uses accessible Source n names in API order', () => {
    render(
      <div>
        {CITATIONS.map((citation, index) => (
          <CitationMarker
            key={citation.chunk_id}
            index={index}
            citation={citation}
          />
        ))}
      </div>,
    )
    const markers = screen.getAllByRole('button', { name: /^source \d+:/i })
    expect(markers.map((marker) => marker.getAttribute('aria-label'))).toEqual([
      'Source 1: alpha-guide.pdf',
      'Source 2: beta-notes.md',
    ])
  })

  it('reveals title, position, and excerpt on focus', async () => {
    const user = userEvent.setup()
    render(<CitationMarker index={0} citation={CITATIONS[0]} />)
    expect(screen.queryByText('alpha beta gamma')).not.toBeInTheDocument()
    await user.tab()
    expect(screen.getByRole('button', { name: /source 1/i })).toHaveFocus()
    expect(screen.getByText('alpha-guide.pdf')).toBeVisible()
    expect(screen.getByText(/position 0/i)).toBeVisible()
    expect(screen.getByText('alpha beta gamma')).toBeVisible()
  })

  it('exposes a citation selection callback seam', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(
      <CitationMarker index={1} citation={CITATIONS[1]} onSelect={onSelect} />,
    )
    await user.click(screen.getByRole('button', { name: /source 2/i }))
    expect(onSelect).toHaveBeenCalledWith(CITATIONS[1], 1)
  })
})
