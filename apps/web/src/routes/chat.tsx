import { useRef, useState } from 'react'
import { type Citation, postChat } from '../api/chat'
import { ApiError } from '../api/client'
import { EmptyState, ErrorState, ForbiddenState } from '../app/shell'
import { Composer } from '../components/Composer'
import { Message } from '../components/Message'
import { SourcePreview } from '../components/SourcePreview'

type SelectedSource = { citations: Citation[]; index: number }

type ThreadItem =
  | { kind: 'user'; id: number; text: string }
  | {
      kind: 'assistant'
      id: number
      answer: string | null
      citations: Citation[]
    }
  | { kind: 'pending'; id: number }

function networkError(): ApiError {
  return new ApiError({
    status: 0,
    code: 'network_error',
    message: 'Network unavailable. Please try again.',
  })
}

/**
 * ODD-3 chat thread. Ephemeral component memory only — no persistence. The
 * user message appends optimistically; the assistant appears only from the
 * POST /api/chat response. While pending, a truthful status shows and the
 * request is abortable. ChatPage owns the selected citation: activating a
 * marker opens SourcePreview over exactly that message's citations array.
 */
export function ChatPage() {
  const [items, setItems] = useState<ThreadItem[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [selected, setSelected] = useState<SelectedSource | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const idRef = useRef(0)
  const lastQueryRef = useRef('')

  function nextId(): number {
    idRef.current += 1
    return idRef.current
  }

  async function send(query: string) {
    const trimmed = query.trim()
    if (trimmed.length === 0 || pending) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    lastQueryRef.current = trimmed
    setPending(true)
    setError(null)
    const userId = nextId()
    const pendingId = nextId()
    setItems((prev) => [
      ...prev,
      { kind: 'user', id: userId, text: trimmed },
      { kind: 'pending', id: pendingId },
    ])
    try {
      const response = await postChat(trimmed, { signal: controller.signal })
      const assistantId = nextId()
      setItems((prev) => [
        ...prev.filter((item) => item.id !== pendingId),
        {
          kind: 'assistant',
          id: assistantId,
          answer: response.answer,
          citations: response.citations ?? [],
        },
      ])
    } catch (err) {
      setItems((prev) => prev.filter((item) => item.id !== pendingId))
      // Abort (user cancellation) is not an error surface.
      if (err instanceof DOMException && err.name === 'AbortError') return
      // 401 is handled globally by apiFetch → router redirect to /login.
      if (err instanceof ApiError && err.status === 401) return
      setError(err instanceof ApiError ? err : networkError())
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      setPending(false)
    }
  }

  function cancel() {
    abortRef.current?.abort()
  }

  // Retry resends the last query, which appends a duplicate user message.
  // Collapse the resend: drop the trailing user message before resending.
  async function retryWithoutDuplicate() {
    if (pending) return
    const query = lastQueryRef.current
    if (query.length === 0) return
    setItems((prev) => {
      const last = prev[prev.length - 1]
      if (last?.kind === 'user' && last.text === query) return prev.slice(0, -1)
      return prev
    })
    await send(query)
  }

  const started = items.length > 0

  return (
    <section aria-labelledby="chat-title">
      <h1 id="chat-title">Chat</h1>
      {!started ? (
        <EmptyState
          title="Ask your documents"
          body="Answers come only from documents you can access, with verified sources."
        />
      ) : (
        <ol style={{ listStyle: 'none', padding: 0 }}>
          {items.map((item) =>
            item.kind === 'user' ? (
              <li key={item.id}>
                <Message messageRole="user" text={item.text} />
              </li>
            ) : item.kind === 'assistant' ? (
              <li key={item.id}>
                <Message
                  messageRole="assistant"
                  answer={item.answer}
                  citations={item.citations}
                  onCitationSelect={(_citation, index) =>
                    setSelected({ citations: item.citations, index })
                  }
                />
              </li>
            ) : (
              <li key={item.id}>
                <p role="status">Searching your documents…</p>
              </li>
            ),
          )}
        </ol>
      )}
      {error?.status === 403 ? (
        <ForbiddenState />
      ) : error ? (
        <ErrorState
          code={error.code}
          message={
            error.status === 429 && error.retryAfter !== null
              ? `${error.message} Try again in ${error.retryAfter} seconds.`
              : error.message
          }
          onRetry={retryWithoutDuplicate}
        />
      ) : null}
      <Composer
        pending={pending}
        onSubmit={(query) => void send(query)}
        onCancel={cancel}
      />
      {selected !== null ? (
        <SourcePreview
          citation={selected.citations[selected.index] ?? null}
          citations={selected.citations}
          selectedIndex={selected.index}
          onClose={() => setSelected(null)}
          onPrevious={() =>
            setSelected((prev) =>
              prev !== null && prev.index > 0
                ? { ...prev, index: prev.index - 1 }
                : prev,
            )
          }
          onNext={() =>
            setSelected((prev) =>
              prev !== null && prev.index < prev.citations.length - 1
                ? { ...prev, index: prev.index + 1 }
                : prev,
            )
          }
        />
      ) : null}
    </section>
  )
}
