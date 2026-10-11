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

const CONVERSATIONS = {
  conversations: [
    {
      id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      title: 'First thread',
      created_at: '2026-10-11T00:00:00Z',
      updated_at: '2026-10-11T00:01:00Z',
    },
    {
      id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
      title: 'Second thread',
      created_at: '2026-10-11T00:00:00Z',
      updated_at: '2026-10-11T00:00:00Z',
    },
  ],
}

const DETAIL = {
  id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  title: 'First thread',
  created_at: '2026-10-11T00:00:00Z',
  updated_at: '2026-10-11T00:01:00Z',
  messages: [
    {
      id: 'm1',
      role: 'user',
      content: 'What is alpha?',
      citations: [],
      created_at: '2026-10-11T00:00:30Z',
    },
    {
      id: 'm2',
      role: 'assistant',
      content: 'Alpha guide says so [1].',
      citations: ANSWER.citations,
      created_at: '2026-10-11T00:00:31Z',
    },
  ],
}

/** URL-aware stub: history reads plus stateless/persisted chat sends. */
function historyFetch(calls: { url: string; body: unknown }[]) {
  return vi.fn().mockImplementation((url: string, init: RequestInit = {}) => {
    calls.push({
      url,
      body:
        init.body === undefined ? undefined : JSON.parse(init.body as string),
    })
    if (url === '/api/conversations' && init.method === 'POST')
      return Promise.resolve(jsonResponse(201, CONVERSATIONS.conversations[0]))
    if (url === '/api/conversations' && init.method !== 'DELETE')
      return Promise.resolve(jsonResponse(200, CONVERSATIONS))
    if (url === '/api/conversations/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
      return Promise.resolve(
        init.method === 'DELETE'
          ? new Response(null, { status: 204 })
          : jsonResponse(200, DETAIL),
      )
    if (url === '/api/chat') return Promise.resolve(jsonResponse(200, ANSWER))
    return Promise.resolve(
      jsonResponse(404, { error: { code: 'not_found', message: 'Missing' } }),
    )
  })
}

beforeEach(() => {
  vi.unstubAllGlobals()
})

afterEach(() => {
  cleanup()
})

describe('ChatPage conversation history', () => {
  it('keeps history closed with zero network calls on first render', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<ChatPage />)
    expect(
      screen.getByRole('button', { name: /show conversations/i }),
    ).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('lists conversations newest-first and shows the empty state', async () => {
    const user = userEvent.setup()
    const calls: { url: string; body: unknown }[] = []
    vi.stubGlobal('fetch', historyFetch(calls))
    render(<ChatPage />)

    await user.click(
      screen.getByRole('button', { name: /show conversations/i }),
    )

    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: /open conversation: first thread/i,
        }),
      ).toBeInTheDocument(),
    )
    expect(
      screen.getByRole('button', { name: /open conversation: second thread/i }),
    ).toBeInTheDocument()
    expect(calls[0]).toMatchObject({
      url: '/api/conversations',
      body: undefined,
    })
  })

  it('creates a conversation, selects it, and sends with its id', async () => {
    const user = userEvent.setup()
    const calls: { url: string; body: unknown }[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init: RequestInit = {}) => {
        calls.push({
          url,
          body:
            init.body === undefined
              ? undefined
              : JSON.parse(init.body as string),
        })
        if (url === '/api/conversations' && init.method === 'POST')
          return Promise.resolve(
            jsonResponse(201, {
              id: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
              title: 'New conversation',
              created_at: 't',
              updated_at: 't',
            }),
          )
        if (url === '/api/conversations')
          return Promise.resolve(jsonResponse(200, { conversations: [] }))
        if (url === '/api/chat')
          return Promise.resolve(jsonResponse(200, ANSWER))
        return Promise.resolve(
          jsonResponse(404, {
            error: { code: 'not_found', message: 'Missing' },
          }),
        )
      }),
    )
    render(<ChatPage />)

    await user.click(
      screen.getByRole('button', { name: /show conversations/i }),
    )
    await waitFor(() =>
      expect(screen.getByText(/no conversations yet/i)).toBeInTheDocument(),
    )

    await user.click(screen.getByRole('button', { name: /new conversation/i }))
    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: /open conversation: new conversation/i,
        }),
      ).toHaveAttribute('aria-pressed', 'true'),
    )

    await user.type(
      screen.getByLabelText(/ask a question/i),
      'What is alpha?{enter}',
    )
    await waitFor(() =>
      expect(screen.getByText(/alpha guide says so/i)).toBeInTheDocument(),
    )

    const chatCall = calls.find((call) => call.url === '/api/chat')
    expect(chatCall?.body).toEqual({
      query: 'What is alpha?',
      conversation_id: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
    })
  })

  it('selects a thread and replaces the view with its persisted messages', async () => {
    const user = userEvent.setup()
    const calls: { url: string; body: unknown }[] = []
    vi.stubGlobal('fetch', historyFetch(calls))
    render(<ChatPage />)

    await user.click(
      screen.getByRole('button', { name: /show conversations/i }),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: /open conversation: first thread/i,
        }),
      ).toBeInTheDocument(),
    )

    await user.click(
      screen.getByRole('button', { name: /open conversation: first thread/i }),
    )
    await waitFor(() =>
      expect(screen.getByText('What is alpha?')).toBeInTheDocument(),
    )
    expect(screen.getByText(/alpha guide says so/i)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /open conversation: first thread/i }),
    ).toHaveAttribute('aria-pressed', 'true')
  })

  it('deletes a thread from the list with a neutral state', async () => {
    const user = userEvent.setup()
    const calls: { url: string; body: unknown }[] = []
    vi.stubGlobal('fetch', historyFetch(calls))
    render(<ChatPage />)

    await user.click(
      screen.getByRole('button', { name: /show conversations/i }),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: /open conversation: first thread/i,
        }),
      ).toBeInTheDocument(),
    )

    await user.click(
      screen.getByRole('button', {
        name: /delete conversation: first thread/i,
      }),
    )
    await waitFor(() =>
      expect(
        screen.queryByRole('button', {
          name: /open conversation: first thread/i,
        }),
      ).not.toBeInTheDocument(),
    )
    expect(
      screen.getByRole('button', { name: /open conversation: second thread/i }),
    ).toBeInTheDocument()
    const deleteCall = calls.find(
      (call) =>
        call.url === '/api/conversations/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    )
    expect(deleteCall).toBeDefined()
  })

  it('maps a missing thread to a neutral alert and drops it from the list', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init: RequestInit = {}) => {
        if (url === '/api/conversations' && init.method !== 'DELETE')
          return Promise.resolve(jsonResponse(200, CONVERSATIONS))
        return Promise.resolve(
          jsonResponse(404, {
            error: { code: 'not_found', message: 'Missing' },
          }),
        )
      }),
    )
    render(<ChatPage />)

    await user.click(
      screen.getByRole('button', { name: /show conversations/i }),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: /open conversation: first thread/i,
        }),
      ).toBeInTheDocument(),
    )

    await user.click(
      screen.getByRole('button', { name: /open conversation: first thread/i }),
    )
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/not found/i),
    )
    expect(
      screen.queryByRole('button', {
        name: /open conversation: first thread/i,
      }),
    ).not.toBeInTheDocument()
  })
})
