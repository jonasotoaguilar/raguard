import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from 'react'
import { Button, tokens } from '../app/shell'

/**
 * ODD-2 composer. Enter submits, Shift+Enter inserts a newline, blank input
 * never submits, and the submit path is disabled while a request is pending
 * (cancellation is offered instead) to prevent duplicate sends.
 */
export function Composer({
  pending,
  onSubmit,
  onCancel,
}: {
  pending: boolean
  onSubmit: (query: string) => void
  onCancel?: () => void
}) {
  const [value, setValue] = useState('')
  const blank = value.trim().length === 0
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  function submit() {
    const query = value.trim()
    if (query.length === 0 || pending) return
    onSubmit(query)
    setValue('')
  }

  function onFormSubmit(event: FormEvent) {
    event.preventDefault()
    submit()
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={onFormSubmit}>
      <label htmlFor="chat-composer">Ask a question</label>
      <textarea
        id="chat-composer"
        ref={inputRef}
        rows={3}
        value={value}
        disabled={pending}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask about your documents…"
        style={{
          display: 'block',
          width: '100%',
          background: tokens.surfaceRaised,
          color: tokens.ink,
          border: `1px solid ${tokens.border}`,
          borderRadius: 8,
          padding: '8px 12px',
          overflowWrap: 'anywhere',
        }}
      />
      {pending ? (
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      ) : (
        <Button type="submit" disabled={blank}>
          Send
        </Button>
      )}
    </form>
  )
}
