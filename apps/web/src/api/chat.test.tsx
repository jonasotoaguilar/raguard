import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CHAT_API_PATH, postChat } from './chat'
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
})
