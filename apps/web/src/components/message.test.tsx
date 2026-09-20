import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { Citation } from '../api/chat'
import { Message } from './Message'

afterEach(() => {
  cleanup()
})

const CITATIONS: Citation[] = [
  {
    chunk_id: '11111111-1111-1111-1111-111111111111',
    document_id: '22222222-2222-2222-2222-222222222222',
    document_name: 'alpha-guide.pdf',
    position: 0,
    content: 'alpha beta gamma',
  },
  {
    chunk_id: '33333333-3333-3333-3333-333333333333',
    document_id: '44444444-4444-4444-4444-444444444444',
    document_name: 'beta-notes.md',
    position: 3,
    content: 'beta delta epsilon',
  },
]

describe('Message', () => {
  it('renders untrusted model and citation text as inert text', () => {
    const hostile: Citation = {
      ...CITATIONS[0],
      document_name: '<img src=x onerror=alert(1)>.pdf',
      content: '<script>alert("xss")</script>',
    }
    const { container } = render(
      <Message
        messageRole="assistant"
        answer={'Hi <script>alert("xss")</script> [1].'}
        citations={[hostile]}
      />,
    )
    const body = screen.getByTestId('assistant-message').textContent ?? ''
    expect(body).toContain('alert("xss")')
    expect(body).toContain('[1].')
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(container.innerHTML).not.toContain('<script>')
  })

  it('shows every marker 1:1 in API order', () => {
    render(
      <Message
        messageRole="assistant"
        answer="Both agree [1] [2]."
        citations={CITATIONS}
      />,
    )
    expect(
      screen.getAllByRole('button', { name: /^source \d+:/i }),
    ).toHaveLength(2)
    expect(
      screen.getByRole('button', { name: 'Source 1: alpha-guide.pdf' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Source 2: beta-notes.md' }),
    ).toBeInTheDocument()
  })

  it('shows an ungrounded notice when citations are empty but an answer exists', () => {
    render(
      <Message messageRole="assistant" answer="I think so." citations={[]} />,
    )
    expect(screen.getByText('I think so.')).toBeInTheDocument()
    expect(screen.getByText(/no verified sources found/i)).toBeInTheDocument()
  })

  it('shows neutral copy for a null answer with zero citations', () => {
    render(<Message messageRole="assistant" answer={null} citations={[]} />)
    expect(
      screen.getByText(/no relevant documents found for this question/i),
    ).toBeInTheDocument()
  })

  it('renders user messages as plain text', () => {
    render(
      <Message
        messageRole="user"
        text="What is <b>alpha</b>?"
        answer={null}
        citations={[]}
      />,
    )
    expect(screen.getByText('What is <b>alpha</b>?')).toBeInTheDocument()
  })
})
