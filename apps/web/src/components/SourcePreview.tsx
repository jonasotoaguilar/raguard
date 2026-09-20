import { useEffect, useRef } from 'react'
import type { Citation } from '../api/chat'
import { tokens } from '../app/shell'

export interface SourcePreviewProps {
  citation: Citation | null | undefined
  citations: Citation[]
  selectedIndex: number
  onClose: () => void
  onPrevious: () => void
  onNext: () => void
}

const MISSING_MESSAGE =
  "This source isn't available or you don't have access to it."

/**
 * ODD-3 client-only source preview dialog. All citation fields are untrusted:
 * rendered as inert React text nodes only — never HTML, never links. The
 * parent owns selection state; this component owns dialog behavior (focus in,
 * Escape, Tab trap, focus restore) without the browser-only dialog API so
 * jsdom stays deterministic.
 */
export function SourcePreview({
  citation,
  citations,
  selectedIndex,
  onClose,
  onPrevious,
  onNext,
}: SourcePreviewProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const restoreRef = useRef<Element | null>(null)

  const total = citations.length
  const atStart = selectedIndex <= 0
  const atEnd = selectedIndex >= total - 1
  // A missing citation must never show cached content: disable navigation.
  const navDisabled = citation == null

  useEffect(() => {
    restoreRef.current = document.activeElement
    closeRef.current?.focus()
    return () => {
      const target = restoreRef.current
      if (target instanceof HTMLElement) target.focus()
    }
  }, [])

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.stopPropagation()
      onClose()
      return
    }
    if (event.key !== 'Tab') return
    const root = dialogRef.current
    if (!root) return
    const focusables = Array.from(
      root.querySelectorAll<HTMLElement>('button:not([disabled])'),
    ).filter((el) => el.tabIndex !== -1)
    if (focusables.length === 0) {
      event.preventDefault()
      return
    }
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="source-preview-title"
      onKeyDown={handleKeyDown}
      style={{
        background: tokens.surfaceRaised,
        color: tokens.ink,
        border: `1px solid ${tokens.border}`,
        borderRadius: 8,
        padding: '12px 16px',
        maxWidth: '100%',
        overflowWrap: 'anywhere',
      }}
    >
      {citation == null ? (
        <>
          <h2 id="source-preview-title">Source unavailable</h2>
          <p>{MISSING_MESSAGE}</p>
        </>
      ) : (
        <>
          <h2 id="source-preview-title">{citation.document_name}</h2>
          <p style={{ color: tokens.inkMuted }}>Position {citation.position}</p>
          <blockquote style={{ margin: '8px 0', paddingLeft: 12 }}>
            {citation.content}
          </blockquote>
          <p style={{ color: tokens.inkMuted }}>
            Chunk {selectedIndex + 1} of {total}
          </p>
        </>
      )}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          style={{
            background: tokens.surfaceMuted,
            color: tokens.ink,
            border: `1px solid ${tokens.border}`,
            borderRadius: 8,
            minHeight: 40,
            padding: '0 12px',
            cursor: 'pointer',
          }}
        >
          Close
        </button>
        <button
          type="button"
          onClick={onPrevious}
          disabled={navDisabled || atStart}
          style={{
            background: tokens.surfaceMuted,
            color: tokens.ink,
            border: `1px solid ${tokens.border}`,
            borderRadius: 8,
            minHeight: 40,
            padding: '0 12px',
            cursor: 'pointer',
          }}
        >
          Previous
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={navDisabled || atEnd}
          style={{
            background: tokens.surfaceMuted,
            color: tokens.ink,
            border: `1px solid ${tokens.border}`,
            borderRadius: 8,
            minHeight: 40,
            padding: '0 12px',
            cursor: 'pointer',
          }}
        >
          Next
        </button>
      </div>
    </div>
  )
}
