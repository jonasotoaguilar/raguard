import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  CHAT_API_PATH,
  CONVERSATIONS_API_PATH,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  postChat,
} from './chat'
import { ApiError } from './client'

function jsonResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  })
}

beforeEach(() => {
  vi.unstubAllGlobals()
})

describe('postChat', () => {
  it('POSTs {query} to /api/chat and mirrors the backend response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        answer: 'Alpha says hi [1].',
        citations: [
          {
            chunk_id: '11111111-1111-1111-1111-111111111111',
            document_id: '22222222-2222-2222-2222-222222222222',
            document_name: 'alpha-guide.pdf',
            position: 0,
            content: 'alpha beta gamma',
          },
        ],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await postChat('What is alpha?')

    expect(fetchMock).toHaveBeenCalledWith(
      CHAT_API_PATH,
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      query: 'What is alpha?',
    })
    expect(result.answer).toBe('Alpha says hi [1].')
    expect(result.citations).toHaveLength(1)
    expect(result.citations[0].document_name).toBe('alpha-guide.pdf')
  })

  it('mirrors the neutral no-match payload untouched', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { answer: null, citations: [] })),
    )
    const result = await postChat('omega')
    expect(result).toEqual({ answer: null, citations: [] })
  })

  it('propagates a 403 ApiError without inventing an answer', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(403, {
          error: { code: 'forbidden', message: 'Nope' },
        }),
      ),
    )
    await expect(postChat('alpha')).rejects.toMatchObject({
      status: 403,
      code: 'forbidden',
    })
  })

  it('surfaces Retry-After on 429', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            429,
            { error: { code: 'rate_limited', message: 'Slow down' } },
            { 'retry-after': '30' },
          ),
        ),
    )
    const failure: ApiError = await postChat('alpha').catch((error) => error)
    expect(failure).toBeInstanceOf(ApiError)
    expect(failure.status).toBe(429)
    expect(failure.retryAfter).toBe(30)
  })

  it('forwards an abort signal to the request', async () => {
    const controller = new AbortController()
    const fetchMock = vi.fn().mockImplementation(
      (_url: string, init: RequestInit = {}) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const pending = postChat('alpha', { signal: controller.signal })
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('sends conversation_id only when a conversation is selected', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(200, { answer: 'Hi [1].', citations: [] }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await postChat('alpha', { conversationId: 'conv-1' })

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      query: 'alpha',
      conversation_id: 'conv-1',
    })
  })
})

describe('conversations client', () => {
  it('lists conversations from /api/conversations', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        conversations: [
          { id: 'c1', title: 'First', created_at: 't', updated_at: 't' },
        ],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await listConversations()

    expect(fetchMock).toHaveBeenCalledWith(
      CONVERSATIONS_API_PATH,
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(result.conversations).toHaveLength(1)
  })

  it('creates a conversation with an empty body by default', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(201, {
          id: 'c1',
          title: 'New conversation',
          created_at: 't',
          updated_at: 't',
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const result = await createConversation()

    expect(fetchMock).toHaveBeenCalledWith(
      CONVERSATIONS_API_PATH,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({})
    expect(result.id).toBe('c1')
  })

  it('reads one conversation by encoded id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        id: 'c1',
        title: 'First',
        created_at: 't',
        updated_at: 't',
        messages: [],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await getConversation('c1')

    expect(fetchMock).toHaveBeenCalledWith(
      `${CONVERSATIONS_API_PATH}/c1`,
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(result.messages).toEqual([])
  })

  it('deletes by encoded id and surfaces the neutral 404', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteConversation('c1')

    expect(fetchMock).toHaveBeenCalledWith(
      `${CONVERSATIONS_API_PATH}/c1`,
      expect.objectContaining({ method: 'DELETE' }),
    )

    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(404, {
            error: { code: 'not_found', message: 'Missing' },
          }),
        ),
    )
    await expect(deleteConversation('gone')).rejects.toMatchObject({
      status: 404,
    })
  })
})
