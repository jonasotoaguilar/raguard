import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Dropzone, MAX_UPLOAD_BYTES } from './Dropzone'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function makeFile(name: string, type: string, size = 16): File {
  const file = new File([new Uint8Array(size)], name, { type })
  if (size !== 16) {
    // Fake large sizes without allocating 20 MiB buffers.
    vi.spyOn(file, 'size', 'get').mockReturnValue(size)
  }
  return file
}

function dropOnTarget(target: HTMLElement, files: File[]) {
  fireEvent.drop(target, {
    dataTransfer: { files, types: ['Files'] },
  })
}

describe('Dropzone', () => {
  it('exposes a real labelled file input', () => {
    render(<Dropzone onFiles={vi.fn()} />)
    expect(screen.getByLabelText(/choose document files/i)).toBeInTheDocument()
  })

  it('accepts valid pdf and markdown files via the input', async () => {
    const onFiles = vi.fn()
    render(<Dropzone onFiles={onFiles} />)
    fireEvent.change(screen.getByLabelText(/choose document files/i), {
      target: {
        files: [
          makeFile('a.pdf', 'application/pdf'),
          makeFile('b.md', 'text/markdown'),
          makeFile('c.markdown', 'text/markdown'),
        ],
      },
    })
    expect(onFiles).toHaveBeenCalledTimes(1)
    expect(onFiles.mock.calls[0][0].map((f: File) => f.name)).toEqual([
      'a.pdf',
      'b.md',
      'c.markdown',
    ])
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('rejects unsupported extensions with an actionable error', () => {
    const onFiles = vi.fn()
    render(<Dropzone onFiles={onFiles} />)
    dropOnTarget(screen.getByTestId('dropzone-target'), [
      makeFile('evil.exe', 'application/x-msdownload'),
    ])
    expect(onFiles).not.toHaveBeenCalled()
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toMatch(/evil\.exe/)
    expect(alert.textContent).toMatch(/\.pdf.*\.md.*\.markdown/)
  })

  it('rejects mismatched MIME types', () => {
    const onFiles = vi.fn()
    render(<Dropzone onFiles={onFiles} />)
    dropOnTarget(screen.getByTestId('dropzone-target'), [
      makeFile('fake.pdf', 'image/png'),
    ])
    expect(onFiles).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('rejects oversize files and names the 20 MiB bound', () => {
    const onFiles = vi.fn()
    render(<Dropzone onFiles={onFiles} />)
    dropOnTarget(screen.getByTestId('dropzone-target'), [
      makeFile('big.pdf', 'application/pdf', MAX_UPLOAD_BYTES + 1),
    ])
    expect(onFiles).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toMatch(/20 MiB/)
  })

  it('accepts a file at exactly the size boundary', () => {
    const onFiles = vi.fn()
    render(<Dropzone onFiles={onFiles} />)
    dropOnTarget(screen.getByTestId('dropzone-target'), [
      makeFile('edge.pdf', 'application/pdf', MAX_UPLOAD_BYTES),
    ])
    expect(onFiles).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('preserves valid files while reporting rejected ones', () => {
    const onFiles = vi.fn()
    render(<Dropzone onFiles={onFiles} />)
    dropOnTarget(screen.getByTestId('dropzone-target'), [
      makeFile('good.pdf', 'application/pdf'),
      makeFile('bad.txt', 'text/plain'),
    ])
    expect(onFiles.mock.calls[0][0].map((f: File) => f.name)).toEqual([
      'good.pdf',
    ])
    expect(screen.getByRole('alert').textContent).toMatch(/bad\.txt/)
  })

  it('exposes a native button target that opens the file dialog on activation', () => {
    render(<Dropzone onFiles={vi.fn()} />)
    const input = screen.getByLabelText(
      /choose document files/i,
    ) as HTMLInputElement
    const clickSpy = vi.spyOn(input, 'click').mockImplementation(() => {})
    const target = screen.getByRole('button', { name: /upload documents/i })
    expect(target.tagName).toBe('BUTTON')
    // Native buttons fire click on Enter/Space; jsdom covers the click half.
    fireEvent.click(target)
    fireEvent.click(target)
    expect(clickSpy).toHaveBeenCalledTimes(2)
  })

  it('accepts valid files via drag and drop', () => {
    const onFiles = vi.fn()
    render(<Dropzone onFiles={onFiles} />)
    dropOnTarget(screen.getByTestId('dropzone-target'), [
      makeFile('dropped.md', 'text/markdown'),
    ])
    expect(onFiles.mock.calls[0][0][0].name).toBe('dropped.md')
  })
})
