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

const TWO_CITATIONS = {
  answer: 'Alpha and beta agree [1] [2].',
  citations: [
    {
      chunk_id: '11111111-1111-1111-1111-111111111111',
      document_id: '22222222-2222-2222-2222-222222222222',
      document_name: 'alpha-guide.pdf',
      position: 0,
      content: 'alpha beta gamma passage',
    },
    {
      chunk_id: '33333333-3333-3333-3333-333333333333',
      document_id: '44444444-4444-4444-4444-444444444444',
      document_name: 'beta-notes.md',
      position: 3,
      content: 'beta delta epsilon passage',
    },
  ],
}

const FIRST_ANSWER = {
  answer: 'First says so [1].',
  citations: [
    {
      chunk_id: '11111111-1111-1111-1111-111111111111',
      document_id: '22222222-2222-2222-2222-222222222222',
      document_name: 'alpha-guide.pdf',
      position: 0,
      content: 'alpha first passage',
    },
  ],
}

const SECOND_ANSWER = {
  answer: 'Second says so [1].',
  citations: [
    {
      chunk_id: '55555555-5555-5555-5555-555555555555',
      document_id: '66666666-6666-6666-6666-666666666666',
      document_name: 'beta-manual.pdf',
      position: 7,
      content: 'beta second passage',
    },
  ],
}

const HOSTILE_ANSWER = {
  answer: 'Evil says so [1].',
  citations: [
    {
      chunk_id: '77777777-7777-7777-7777-777777777777',
      document_id: '88888888-8888-8888-8888-888888888888',
      document_name: 'evil.pdf',
      position: 0,
      content: '<script>alert(1)</script><a href="https://evil.test">click</a>',
    },
  ],
}

async function askQuestion(
  user: ReturnType<typeof userEvent.setup>,
  text: string,
) {
  await user.type(screen.getByLabelText(/ask a question/i), `${text}{enter}`)
}

describe('ChatPage source preview', () => {
  it('opens a labelled dialog from the marker with chunk context', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, TWO_CITATIONS)),
    )
    render(<ChatPage />)
    await askQuestion(user, 'What do they say?')
    await waitFor(() =>
      expect(screen.getByText(/alpha and beta agree/i)).toBeInTheDocument(),
    )

    await user.click(
      screen.getByRole('button', { name: 'Source 1: alpha-guide.pdf' }),
    )
    const dialog = screen.getByRole('dialog', { name: /alpha-guide\.pdf/i })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(
      screen.getByRole('heading', { name: /alpha-guide\.pdf/i }),
    ).toBeVisible()
    expect(screen.getByText('alpha beta gamma passage')).toBeVisible()
    expect(screen.getByText(/position 0/i)).toBeVisible()
    expect(screen.getByText(/chunk 1 of 2/i)).toBeVisible()
  })

  it('keeps Previous/Next bounded within the message citations', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, TWO_CITATIONS)),
    )
    render(<ChatPage />)
    await askQuestion(user, 'What do they say?')
    await waitFor(() =>
      expect(screen.getByText(/alpha and beta agree/i)).toBeInTheDocument(),
    )

    await user.click(
      screen.getByRole('button', { name: 'Source 1: alpha-guide.pdf' }),
    )
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /next/i })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByText('beta delta epsilon passage')).toBeVisible()
    expect(screen.getByText(/chunk 2 of 2/i)).toBeVisible()
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: /previous/i }))
    expect(screen.getByText('alpha beta gamma passage')).toBeVisible()
    expect(screen.getByText(/chunk 1 of 2/i)).toBeVisible()
  })

  it('scopes the preview to the activated assistant message', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(200, FIRST_ANSWER))
        .mockResolvedValueOnce(jsonResponse(200, SECOND_ANSWER)),
    )
    render(<ChatPage />)
    await askQuestion(user, 'first question')
    await waitFor(() =>
      expect(screen.getByText(/first says so/i)).toBeInTheDocument(),
    )
    await askQuestion(user, 'second question')
    await waitFor(() =>
      expect(screen.getByText(/second says so/i)).toBeInTheDocument(),
    )

    await user.click(
      screen.getByRole('button', { name: 'Source 1: beta-manual.pdf' }),
    )
    const dialog = screen.getByRole('dialog', { name: /beta-manual\.pdf/i })
    expect(dialog).toBeVisible()
    expect(screen.getByText('beta second passage')).toBeVisible()
    expect(screen.getByText(/chunk 1 of 1/i)).toBeVisible()
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled()
  })

  it('closes on Escape and returns focus to the marker', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, ANSWER)))
    render(<ChatPage />)
    await askQuestion(user, 'What is alpha?')
    await waitFor(() =>
      expect(screen.getByText(/alpha guide says so/i)).toBeInTheDocument(),
    )

    const marker = screen.getByRole('button', {
      name: 'Source 1: alpha-guide.pdf',
    })
    await user.click(marker)
    expect(screen.getByRole('dialog')).toBeVisible()
    expect(screen.getByRole('button', { name: /close/i })).toHaveFocus()

    await user.keyboard('{Escape}')
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(
      screen.getByRole('button', { name: 'Source 1: alpha-guide.pdf' }),
    ).toHaveFocus()
  })

  it('closes from the Close button and unmounts the dialog', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, ANSWER)))
    render(<ChatPage />)
    await askQuestion(user, 'What is alpha?')
    await waitFor(() =>
      expect(screen.getByText(/alpha guide says so/i)).toBeInTheDocument(),
    )

    await user.click(
      screen.getByRole('button', { name: 'Source 1: alpha-guide.pdf' }),
    )
    expect(screen.getByRole('dialog')).toBeVisible()
    await user.click(screen.getByRole('button', { name: /close/i }))
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(
      screen.getByRole('button', { name: 'Source 1: alpha-guide.pdf' }),
    ).toHaveFocus()
  })

  it('renders hostile citation text as inert text without markup', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, HOSTILE_ANSWER)),
    )
    const { container } = render(<ChatPage />)
    await askQuestion(user, 'What is evil?')
    await waitFor(() =>
      expect(screen.getByText(/evil says so/i)).toBeInTheDocument(),
    )

    await user.click(screen.getByRole('button', { name: 'Source 1: evil.pdf' }))
    expect(
      screen.getByText(
        '<script>alert(1)</script><a href="https://evil.test">click</a>',
      ),
    ).toBeVisible()
    expect(container.querySelector('a')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
  })
})
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
