/** ODD-2 chat API: stateless POST /api/chat through the shared apiFetch. */
import { apiFetch } from './client'

export interface Citation {
  chunk_id: string
  document_id: string
  document_name: string
  position: number
  content: string
}

export interface ChatResponse {
  answer: string | null
  citations: Citation[]
}

export const CHAT_API_PATH = '/api/chat'
export const CONVERSATIONS_API_PATH = '/api/conversations'

/**
 * Send one query; stateless unless `conversationId` selects an owned thread.
 * The key is omitted (not null) for stateless sends so the backend performs
 * zero writes; with a conversation the backend persists both turns.
 */
export function postChat(
  query: string,
  init: { signal?: AbortSignal; conversationId?: string } = {},
): Promise<ChatResponse> {
  return apiFetch<ChatResponse>(CHAT_API_PATH, {
    method: 'POST',
    body: JSON.stringify(
      init.conversationId === undefined
        ? { query }
        : { query, conversation_id: init.conversationId },
    ),
    signal: init.signal,
  })
}

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationList {
  conversations: ConversationSummary[]
}

export interface HistoryMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  created_at: string
}

export interface ConversationDetail extends ConversationSummary {
  messages: HistoryMessage[]
}

/** List the caller's own conversations, newest first. */
export function listConversations(
  init: { signal?: AbortSignal } = {},
): Promise<ConversationList> {
  return apiFetch<ConversationList>(CONVERSATIONS_API_PATH, {
    signal: init.signal,
  })
}

/** Create a thread; the title defaults server-side when omitted. */
export function createConversation(
  init: { title?: string; signal?: AbortSignal } = {},
): Promise<ConversationSummary> {
  return apiFetch<ConversationSummary>(CONVERSATIONS_API_PATH, {
    method: 'POST',
    body: JSON.stringify(init.title === undefined ? {} : { title: init.title }),
    signal: init.signal,
  })
}

/** Read one owned thread with messages in chronological order. */
export function getConversation(
  id: string,
  init: { signal?: AbortSignal } = {},
): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(
    `${CONVERSATIONS_API_PATH}/${encodeURIComponent(id)}`,
    { signal: init.signal },
  )
}

/** Delete a thread and its messages; unknown ids surface a neutral 404. */
export function deleteConversation(
  id: string,
  init: { signal?: AbortSignal } = {},
): Promise<void> {
  return apiFetch<void>(`${CONVERSATIONS_API_PATH}/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    signal: init.signal,
  })
}
