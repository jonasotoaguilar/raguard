import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatPage } from './chat'

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

const ANSWER = {
  answer: 'Alpha guide says so [1].',
  citations: [
    {
      chunk_id: '11111111-1111-1111-1111-111111111111',
      document_id: '22222222-2222-2222-2222-222222222222',
      document_name: 'alpha-guide.pdf',
      position: 0,
      content: 'alpha beta gamma',
    },
  ],
}

/** Never-resolving fetch mock: rejects with AbortError only when the signal fires. */
function abortableFetch() {
  return vi.fn().mockImplementation(
    (_url: string, init: RequestInit = {}) =>
      new Promise<Response>((_resolve, reject) => {
        if (init.signal?.aborted) {
          reject(new DOMException('Aborted', 'AbortError'))
          return
        }
        init.signal?.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError')),
        )
      }),
  )
}

beforeEach(() => {
  vi.unstubAllGlobals()
})

afterEach(() => {
  cleanup()
})

describe('ChatPage thread', () => {
  it('starts with a neutral empty state and no network calls', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<ChatPage />)
    expect(screen.getByLabelText(/ask your documents/i)).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('appends the user message optimistically and renders the assistant only from the response', async () => {
    const user = userEvent.setup()
    let resolveFetch!: (response: Response) => void
    const gate = new Promise<Response>((resolve) => {
      resolveFetch = resolve
    })
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(gate))
    render(<ChatPage />)

    await user.type(
      screen.getByLabelText(/ask a question/i),
      'What is alpha?{enter}',
    )

    // Optimistic user message plus a truthful pending status — and no answer yet.
    expect(screen.getByText('What is alpha?')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      /searching your documents/i,
    )
    expect(screen.queryByText(/alpha guide says so/i)).not.toBeInTheDocument()

    resolveFetch(jsonResponse(200, ANSWER))
    await waitFor(() =>
      expect(screen.getByText(/alpha guide says so/i)).toBeInTheDocument(),
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Source 1: alpha-guide.pdf' }),
    ).toBeInTheDocument()
  })

  it('does not submit empty or whitespace-only queries', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<ChatPage />)
    await user.type(screen.getByLabelText(/ask a question/i), '   {enter}')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('prevents duplicate sends while a request is pending', async () => {
    const user = userEvent.setup()
    let resolveFetch!: (response: Response) => void
    const gate = new Promise<Response>((resolve) => {
      resolveFetch = resolve
    })
    const fetchMock = vi.fn().mockReturnValue(gate)
    vi.stubGlobal('fetch', fetchMock)
    render(<ChatPage />)

    await user.type(screen.getByLabelText(/ask a question/i), 'first{enter}')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await user.type(screen.getByLabelText(/ask a question/i), 'second{enter}')
    expect(fetchMock).toHaveBeenCalledTimes(1)

    resolveFetch(jsonResponse(200, ANSWER))
    await waitFor(() =>
      expect(screen.getByText(/alpha guide says so/i)).toBeInTheDocument(),
    )
  })

  it('cancels the pending request without fabricating an assistant message', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', abortableFetch())
    render(<ChatPage />)

    await user.type(
      screen.getByLabelText(/ask a question/i),
      'What is alpha?{enter}',
    )
    expect(screen.getByRole('status')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() =>
      expect(screen.queryByRole('status')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('What is alpha?')).toBeInTheDocument()
    expect(screen.queryByText(/alpha guide says so/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/error/i)).not.toBeInTheDocument()
  })

  it('renders the neutral no-match copy for a null answer', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(jsonResponse(200, { answer: null, citations: [] })),
    )
    render(<ChatPage />)
    await user.type(screen.getByLabelText(/ask a question/i), 'omega{enter}')
    await waitFor(() =>
      expect(
        screen.getByText(/no relevant documents found for this question/i),
      ).toBeInTheDocument(),
    )
  })

  it('maps 403 to ForbiddenState', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(403, { error: { code: 'forbidden', message: 'Nope' } }),
        ),
    )
    render(<ChatPage />)
    await user.type(screen.getByLabelText(/ask a question/i), 'alpha{enter}')
    await waitFor(() =>
      expect(screen.getByLabelText(/forbidden/i)).toBeInTheDocument(),
    )
    expect(screen.queryByText(/alpha guide says so/i)).not.toBeInTheDocument()
  })

  it('reports 429 with retry-after information and retries', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          429,
          { error: { code: 'rate_limited', message: 'Slow down' } },
          { 'retry-after': '30' },
        ),
      )
      .mockResolvedValueOnce(jsonResponse(200, ANSWER))
    vi.stubGlobal('fetch', fetchMock)
    render(<ChatPage />)
    await user.type(screen.getByLabelText(/ask a question/i), 'alpha{enter}')
    await waitFor(() =>
      expect(screen.getByText(/30 seconds/i)).toBeInTheDocument(),
    )

    await user.click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() =>
      expect(screen.getByText(/alpha guide says so/i)).toBeInTheDocument(),
    )
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('renders a retryable error for 5xx failures without assistant text', async () => {
    const user = userEvent.setup()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(500, {
          error: { code: 'internal_error', message: 'Boom' },
        }),
      )
      .mockResolvedValueOnce(jsonResponse(200, ANSWER))
    vi.stubGlobal('fetch', fetchMock)
    render(<ChatPage />)
    await user.type(screen.getByLabelText(/ask a question/i), 'alpha{enter}')
    await waitFor(() =>
      expect(screen.getByLabelText(/error/i)).toBeInTheDocument(),
    )
    expect(screen.queryByText(/alpha guide says so/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() =>
      expect(screen.getByText(/alpha guide says so/i)).toBeInTheDocument(),
    )
  })
})
