import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Composer } from './Composer'

afterEach(() => {
  cleanup()
})

describe('Composer', () => {
  it('autofocuses the input', async () => {
    render(<Composer pending={false} onSubmit={vi.fn()} />)
    expect(screen.getByLabelText(/ask a question/i)).toHaveFocus()
  })

  it('submits on Enter and clears the box', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Composer pending={false} onSubmit={onSubmit} />)
    await user.type(screen.getByLabelText(/ask a question/i), 'hello{enter}')
    expect(onSubmit).toHaveBeenCalledWith('hello')
    expect(screen.getByLabelText(/ask a question/i)).toHaveValue('')
  })

  it('inserts a newline on Shift+Enter without submitting', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Composer pending={false} onSubmit={onSubmit} />)
    const box = screen.getByLabelText(/ask a question/i)
    await user.type(box, 'line one{shift>}{enter}{/shift}line two')
    expect(onSubmit).not.toHaveBeenCalled()
    expect((box as HTMLTextAreaElement).value).toContain('\n')
  })

  it('ignores empty and whitespace-only queries', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Composer pending={false} onSubmit={onSubmit} />)
    await user.type(screen.getByLabelText(/ask a question/i), '   {enter}')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('blocks duplicate sends while pending and offers cancellation', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const onCancel = vi.fn()
    render(<Composer pending={true} onSubmit={onSubmit} onCancel={onCancel} />)
    // Send is replaced by Cancel and the box is locked: no second submit path.
    expect(
      screen.queryByRole('button', { name: /send/i }),
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText(/ask a question/i)).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
