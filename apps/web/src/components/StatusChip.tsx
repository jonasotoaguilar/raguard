import { tokens } from '../app/shell'

/**
 * ODD-4 status chip. Renders the four DESIGN vocabulary states with text plus
 * a glyph marker — never color-only. The API currently returns
 * pending/indexed/failed; `indexing` is accepted for forward-compatible
 * display. Failure reasons are untrusted API text rendered as inert nodes.
 */
export type ChipStatus = 'pending' | 'indexing' | 'indexed' | 'failed'

const META: Record<
  ChipStatus,
  { label: string; icon: string; color: string; background: string }
> = {
  pending: {
    label: 'Pending',
    icon: '○',
    color: tokens.inkMuted,
    background: tokens.surfaceRaised,
  },
  indexing: {
    label: 'Indexing',
    icon: '◐',
    color: tokens.primary,
    background: tokens.surfaceRaised,
  },
  indexed: {
    label: 'Indexed',
    icon: '●',
    color: tokens.ink,
    background: tokens.surfaceMuted,
  },
  failed: {
    label: 'Failed',
    icon: '✕',
    color: tokens.danger,
    background: tokens.onDanger,
  },
}

export function StatusChip({
  status,
  failureReason,
}: {
  status: ChipStatus
  failureReason?: string | null
}) {
  const meta = META[status]
  return (
    <span
      data-testid="status-chip"
      data-status={status}
      style={{
        display: 'inline-block',
        background: meta.background,
        color: meta.color,
        border: `1px solid ${tokens.border}`,
        borderRadius: 999,
        padding: '2px 10px',
        overflowWrap: 'anywhere',
        maxWidth: '100%',
      }}
    >
      <span aria-hidden="true">{meta.icon}</span> {meta.label}
      {status === 'failed' && failureReason ? (
        <span data-testid="status-chip-reason">: {failureReason}</span>
      ) : null}
    </span>
  )
}
