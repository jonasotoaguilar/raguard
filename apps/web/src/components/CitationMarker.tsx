import { useState } from 'react'
import type { Citation } from '../api/chat'
import { tokens } from '../app/shell'

export type CitationSelection = (citation: Citation, index: number) => void

/**
 * ODD-2 [n] marker. The button is the 1:1 citation handle; focus/hover shows a
 * small read-only popover (title, position, excerpt). No links, no HTML.
 */
export function CitationMarker({
  index,
  citation,
  onSelect,
}: {
  index: number
  citation: Citation
  onSelect?: CitationSelection
}) {
  const [open, setOpen] = useState(false)
  const label = `Source ${index + 1}: ${citation.document_name}`
  return (
    <span style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        aria-label={label}
        aria-expanded={open || undefined}
        onClick={() => onSelect?.(citation, index)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        style={{
          background: tokens.surfaceMuted,
          color: tokens.primary,
          border: `1px solid ${tokens.border}`,
          borderRadius: 4,
          padding: '0 4px',
          minHeight: 24,
          cursor: 'pointer',
        }}
      >
        [{index + 1}]
      </button>
      {open ? (
        <span
          role="note"
          aria-label={`${citation.document_name} excerpt`}
          style={{
            position: 'absolute',
            zIndex: 10,
            bottom: '100%',
            left: 0,
            maxWidth: 280,
            background: tokens.surfaceRaised,
            color: tokens.ink,
            border: `1px solid ${tokens.border}`,
            borderRadius: 8,
            padding: 8,
            overflowWrap: 'anywhere',
          }}
        >
          <strong style={{ display: 'block' }}>{citation.document_name}</strong>
          <span style={{ display: 'block', color: tokens.inkMuted }}>
            Position {citation.position}
          </span>
          <span style={{ display: 'block' }}>{citation.content}</span>
        </span>
      ) : null}
    </span>
  )
}
