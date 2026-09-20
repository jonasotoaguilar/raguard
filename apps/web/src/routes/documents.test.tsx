import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { listDocuments, uploadDocument } from '../api/documents'
import {
  DOCUMENTS_POLL_MS,
  DOCUMENTS_QUERY_KEY,
  type DocumentList,
  DocumentsPage,
  documentsPollInterval,
  documentsQueryOptions,
} from './documents'

vi.mock('../api/documents', () => ({
  listDocuments: vi.fn(),
  uploadDocument: vi.fn(),
}))

const listMock = vi.mocked(listDocuments)
const uploadMock = vi.mocked(uploadDocument)

const INDEXED = {
  id: '11111111-1111-1111-1111-111111111111',
  name: 'alpha.pdf',
  status: 'indexed',
  failure_reason: null,
} as const

const FAILED = {
  id: '22222222-2222-2222-2222-222222222222',
  name: 'beta.md',
  status: 'failed',
  failure_reason: 'malformed',
} as const

const PENDING = {
  id: '33333333-3333-3333-3333-333333333333',
  name: 'gamma.pdf',
  status: 'pending',
  failure_reason: null,
} as const

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <DocumentsPage />
    </QueryClientProvider>,
  )
}

const mdFile = (name: string): File =>
  new File(['# notes'], name, { type: 'text/markdown' })

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  cleanup()
})

describe('DocumentsPage list', () => {
  it('renders the heading, scoped headers, chips, and detail links', async () => {
    listMock.mockResolvedValue({ documents: [INDEXED, FAILED] } as never)
    const { container } = renderPage()

    expect(
      screen.getByRole('heading', { name: /documents/i }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByText('alpha.pdf')).toBeInTheDocument(),
    )

    const headers = screen.getAllByRole('columnheader')
    expect(headers.map((h) => h.textContent)).toEqual(['Name', 'Status'])
    for (const h of headers) expect(h.getAttribute('scope')).toBe('col')

    expect(screen.getByText('Indexed')).toBeInTheDocument()
    expect(screen.getByText(/Failed/)).toBeInTheDocument()
    expect(screen.getByText(/malformed/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'alpha.pdf' })).toHaveAttribute(
      'href',
      '/documents/11111111-1111-1111-1111-111111111111',
    )
  })

  it('renders untrusted names as inert text without markup', async () => {
    listMock.mockResolvedValue({
      documents: [
        {
          id: '44444444-4444-4444-4444-444444444444',
          name: '<script>alert(1)</script>.pdf',
          status: 'indexed',
          failure_reason: '<b>boom</b>',
        },
      ],
    } as never)
    const { container } = renderPage()

    await waitFor(() =>
      expect(
        screen.getByText('<script>alert(1)</script>.pdf'),
      ).toBeInTheDocument(),
    )
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
  })

  it('shows a neutral empty state that points at the Dropzone', async () => {
    listMock.mockResolvedValue({ documents: [] })
    renderPage()

    await waitFor(() =>
      expect(screen.getByText(/no documents yet/i)).toBeInTheDocument(),
    )
    expect(screen.getByTestId('dropzone-target')).toBeInTheDocument()
    expect(screen.queryByLabelText(/error/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/forbidden/i)).not.toBeInTheDocument()
  })

  it('maps 403 to ForbiddenState without existence disclosure', async () => {
    listMock.mockRejectedValue(
      new ApiError({ status: 403, code: 'forbidden', message: 'Nope' }),
    )
    renderPage()

    await waitFor(() =>
      expect(screen.getByLabelText(/forbidden/i)).toBeInTheDocument(),
    )
    expect(
      screen.queryByRole('button', { name: /retry/i }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('alpha.pdf')).not.toBeInTheDocument()
  })

  it('shows a retryable error for 5xx and recovers on retry', async () => {
    listMock
      .mockRejectedValueOnce(
        new ApiError({ status: 500, code: 'internal_error', message: 'Boom' }),
      )
      .mockResolvedValueOnce({ documents: [] })
    renderPage()

    await waitFor(() =>
      expect(screen.getByLabelText(/error/i)).toBeInTheDocument(),
    )
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() =>
      expect(screen.getByText(/no documents yet/i)).toBeInTheDocument(),
    )
    expect(listMock).toHaveBeenCalledTimes(2)
  })
})

describe('DocumentsPage upload', () => {
  it('uploads valid files, disables the Dropzone mid-flight, then refreshes', async () => {
    listMock
      .mockResolvedValueOnce({ documents: [INDEXED] } as never)
      .mockResolvedValueOnce({ documents: [INDEXED, PENDING] } as never)
    let release!: (doc: unknown) => void
    uploadMock.mockReturnValue(
      new Promise((resolve) => {
        release = resolve
      }) as never,
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('alpha.pdf')).toBeInTheDocument(),
    )

    await user.upload(screen.getByTestId('dropzone-input'), mdFile('new.md'))
    await waitFor(() =>
      expect(screen.getByTestId('dropzone-target')).toBeDisabled(),
    )
    expect(uploadMock).toHaveBeenCalledTimes(1)
    expect(uploadMock.mock.calls[0][0]).toBeInstanceOf(File)

    release({ ...PENDING, name: 'new.md' })
    await waitFor(() =>
      expect(screen.getByText('gamma.pdf')).toBeInTheDocument(),
    )
    expect(listMock).toHaveBeenCalledTimes(2)
    await waitFor(() =>
      expect(screen.getByTestId('dropzone-target')).toBeEnabled(),
    )
  })

  it('surfaces a calm upload error while keeping existing documents', async () => {
    listMock.mockResolvedValue({ documents: [INDEXED] } as never)
    uploadMock.mockRejectedValue(
      new ApiError({
        status: 400,
        code: 'invalid_request',
        message: 'Unsupported file type',
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('alpha.pdf')).toBeInTheDocument(),
    )

    await user.upload(screen.getByTestId('dropzone-input'), mdFile('bad.md'))
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent(/try again/i)
    // Already listed documents survive the failed upload.
    expect(screen.getByText('alpha.pdf')).toBeInTheDocument()
    expect(uploadMock).toHaveBeenCalledTimes(1)
  })

  it('prevents duplicate sends while an upload is in flight', async () => {
    listMock.mockResolvedValue({ documents: [] })
    uploadMock.mockReturnValue(new Promise(() => {}) as never)
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      expect(screen.getByTestId('dropzone-target')).toBeInTheDocument(),
    )

    await user.upload(screen.getByTestId('dropzone-input'), mdFile('one.md'))
    await waitFor(() =>
      expect(screen.getByTestId('dropzone-target')).toBeDisabled(),
    )
    // A disabled Dropzone cannot accept a second batch mid-flight.
    expect(uploadMock).toHaveBeenCalledTimes(1)
  })
})

describe('DocumentsPage polling options', () => {
  const pendingList = { documents: [PENDING] } as unknown as DocumentList
  const indexingList = {
    documents: [{ ...PENDING, status: 'indexing' }],
  } as unknown as DocumentList
  const idleList = { documents: [INDEXED, FAILED] } as unknown as DocumentList

  it('uses the documents query key and a 5s poll interval', () => {
    expect([...DOCUMENTS_QUERY_KEY]).toEqual(['documents'])
    expect(DOCUMENTS_POLL_MS).toBe(5000)
  })

  it('polls while pending or indexing, stops when idle', () => {
    expect(documentsPollInterval(pendingList)).toBe(5000)
    expect(documentsPollInterval(indexingList)).toBe(5000)
    expect(documentsPollInterval(idleList)).toBe(false)
    expect(documentsPollInterval({ documents: [] })).toBe(false)
    expect(documentsPollInterval(undefined)).toBe(false)
  })

  it('exposes focus/background polling options on the query', () => {
    const options = documentsQueryOptions()
    expect(options.queryKey).toEqual(['documents'])
    expect(options.refetchOnWindowFocus).toBe(true)
    expect(options.refetchIntervalInBackground).toBe(false)
    expect(typeof options.refetchInterval).toBe('function')
  })
})
