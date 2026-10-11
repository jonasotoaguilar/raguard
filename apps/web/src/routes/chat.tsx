import { useRef, useState } from 'react'
import {
  type Citation,
  type ConversationSummary,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  postChat,
} from '../api/chat'
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
 * ODD-3 chat thread with optional F2 history. The thread stays ephemeral by
 * default: the user message appends optimistically and the assistant appears
 * only from the POST /api/chat response. Opening the conversations panel
 * loads the caller's own threads; selecting one replaces the thread with its
 * persisted messages and subsequent sends carry its `conversation_id` so the
 * backend persists both turns. Without a selected conversation sends stay
 * stateless with zero server writes. While pending, a truthful status shows
 * and the request is abortable. ChatPage owns the selected citation:
 * activating a marker opens SourcePreview over exactly that message's
 * citations array.
 */
export function ChatPage() {
  const [items, setItems] = useState<ThreadItem[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [selected, setSelected] = useState<SelectedSource | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
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
      const response = await postChat(trimmed, {
        signal: controller.signal,
        conversationId: selectedId ?? undefined,
      })
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

  function neutralHistoryError(err: unknown): string {
    if (err instanceof ApiError && err.status === 404)
      return 'Conversation not found. It may have been deleted.'
    if (err instanceof ApiError) return err.message
    return 'Network unavailable. Please try again.'
  }

  async function toggleHistory() {
    const next = !historyOpen
    setHistoryOpen(next)
    if (!next) return
    setHistoryLoading(true)
    setHistoryError(null)
    try {
      const list = await listConversations()
      setConversations(list.conversations ?? [])
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return
      setHistoryError(neutralHistoryError(err))
    } finally {
      setHistoryLoading(false)
    }
  }

  async function createSelectedConversation() {
    setHistoryError(null)
    try {
      const created = await createConversation()
      setConversations((prev) => [created, ...prev])
      setSelectedId(created.id)
      setItems([])
      setError(null)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return
      setHistoryError(neutralHistoryError(err))
    }
  }

  async function selectConversation(id: string) {
    setHistoryError(null)
    try {
      const detail = await getConversation(id)
      setSelectedId(detail.id)
      setError(null)
      setItems(
        detail.messages.map((message, index) =>
          message.role === 'user'
            ? { kind: 'user' as const, id: index + 1, text: message.content }
            : {
                kind: 'assistant' as const,
                id: index + 1,
                answer: message.content.length > 0 ? message.content : null,
                citations: message.citations ?? [],
              },
        ),
      )
      idRef.current = detail.messages.length
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return
      if (err instanceof ApiError && err.status === 404)
        setConversations((prev) => prev.filter((row) => row.id !== id))
      setHistoryError(neutralHistoryError(err))
    }
  }

  async function removeConversation(id: string) {
    setHistoryError(null)
    try {
      await deleteConversation(id)
      setConversations((prev) => prev.filter((row) => row.id !== id))
      if (selectedId === id) setSelectedId(null)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return
      if (err instanceof ApiError && err.status === 404)
        setConversations((prev) => prev.filter((row) => row.id !== id))
      setHistoryError(neutralHistoryError(err))
    }
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
      <button type="button" onClick={() => void toggleHistory()}>
        {historyOpen ? 'Hide conversations' : 'Show conversations'}
      </button>
      {historyOpen ? (
        <section aria-label="Conversations">
          <button
            type="button"
            onClick={() => void createSelectedConversation()}
          >
            New conversation
          </button>
          {historyLoading ? (
            <p role="status">Loading conversations…</p>
          ) : historyError !== null ? (
            <p role="alert">{historyError}</p>
          ) : conversations.length === 0 ? (
            <p>No conversations yet.</p>
          ) : (
            <ul>
              {conversations.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    aria-pressed={selectedId === row.id}
                    onClick={() => void selectConversation(row.id)}
                  >
                    Open conversation: {row.title}
                  </button>{' '}
                  <button
                    type="button"
                    onClick={() => void removeConversation(row.id)}
                  >
                    Delete conversation: {row.title}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
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
