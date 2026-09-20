import type { Citation } from '../api/chat'
import { tokens } from '../app/shell'
import { CitationMarker, type CitationSelection } from './CitationMarker'

/**
 * ODD-2 thread message. All API/model/citation text is untrusted: rendered as
 * inert React text nodes only — never HTML. Markers map 1:1 in API order.
 */
export function Message({
  messageRole,
  text,
  answer,
  citations,
  onCitationSelect,
}: {
  messageRole: 'user' | 'assistant'
  text?: string
  answer?: string | null
  citations?: Citation[]
  onCitationSelect?: CitationSelection
}) {
  if (messageRole === 'user') {
    return (
      <div
        data-testid="user-message"
        style={{
          background: tokens.surfaceRaised,
          border: `1px solid ${tokens.border}`,
          borderRadius: 8,
          padding: '8px 12px',
          overflowWrap: 'anywhere',
        }}
      >
        <p style={{ margin: 0 }}>{text}</p>
      </div>
    )
  }

  const cites = citations ?? []
  if (answer === null && cites.length === 0) {
    return (
      <p style={{ overflowWrap: 'anywhere' }}>
        No relevant documents found for this question. Try rephrasing, or ask an
        admin if you expected access.
      </p>
    )
  }
  return (
    <div data-testid="assistant-message" style={{ overflowWrap: 'anywhere' }}>
      {answer !== null && answer !== undefined ? <p>{answer}</p> : null}
      {cites.length > 0 ? (
        <section
          aria-label="Sources"
          style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}
        >
          {cites.map((citation, index) => (
            <CitationMarker
              key={citation.chunk_id}
              index={index}
              citation={citation}
              onSelect={onCitationSelect}
            />
          ))}
        </section>
      ) : (
        <p style={{ color: tokens.inkMuted }}>No verified sources found</p>
      )}
    </div>
  )
}
