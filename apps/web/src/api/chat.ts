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

/** Send one stateless query; mirrors `{answer, citations}` with no local persistence. */
export function postChat(
  query: string,
  init: { signal?: AbortSignal } = {},
): Promise<ChatResponse> {
  return apiFetch<ChatResponse>(CHAT_API_PATH, {
    method: 'POST',
    body: JSON.stringify({ query }),
    signal: init.signal,
  })
}
