import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, clearSession, setSession } from '../api/client'
import { getDocument } from '../api/documents'
import { documentDetailRoute, router } from '../app/router'
import { DocumentDetailPage, documentDetailQueryOptions } from './documents'

vi.mock('../api/documents', () => ({
  listDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  getDocument: vi.fn(),
}))

const getMock = vi.mocked(getDocument)

const DOC_ID = '11111111-1111-1111-1111-111111111111'

const INDEXED = {
  id: DOC_ID,
  name: 'alpha.pdf',
  status: 'indexed',
  failure_reason: null,
} as const

function renderDetail(documentId: string = DOC_ID) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <DocumentDetailPage documentId={documentId} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  clearSession()
})

afterEach(() => {
  cleanup()
  clearSession()
})

describe('DocumentDetailPage success', () => {
  it('renders the document name, status chip, id metadata, and back link', async () => {
    getMock.mockResolvedValue(INDEXED as never)
    renderDetail()

    expect(
      await screen.findByRole('heading', { name: 'alpha.pdf' }),
    ).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Indexed')).toBeInTheDocument())
    expect(screen.getByText(DOC_ID)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /back to documents/i }),
    ).toHaveAttribute('href', '/documents')
  })

  it('uses the document query key and forwards the id to getDocument', async () => {
    getMock.mockResolvedValue(INDEXED as never)
    const options = documentDetailQueryOptions(DOC_ID)

    expect([...(options.queryKey as readonly unknown[])]).toEqual([
      'document',
      DOC_ID,
    ])

    const controller = new AbortController()
    await options.queryFn?.({ signal: controller.signal } as never)
    expect(getMock).toHaveBeenCalledWith(
      DOC_ID,
      expect.objectContaining({ signal: controller.signal }),
    )
  })

  it('renders failure reasons as inert text without markup', async () => {
    getMock.mockResolvedValue({
      id: DOC_ID,
      name: '<script>alert(1)</script>.pdf',
      status: 'failed',
      failure_reason: '<b>boom</b>',
    } as never)
    const { container } = renderDetail()

    await waitFor(() =>
      expect(
        screen.getByText('<script>alert(1)</script>.pdf'),
      ).toBeInTheDocument(),
    )
    expect(screen.getByText(/<b>boom<\/b>/)).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
  })
})

describe('DocumentDetailPage errors', () => {
  it('maps 403 to ForbiddenState without a retry', async () => {
    getMock.mockRejectedValue(
      new ApiError({ status: 403, code: 'forbidden', message: 'Nope' }),
    )
    renderDetail()

    await waitFor(() =>
      expect(screen.getByLabelText(/forbidden/i)).toBeInTheDocument(),
    )
    expect(
      screen.queryByRole('button', { name: /retry/i }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('alpha.pdf')).not.toBeInTheDocument()
  })

  it('maps 404 to neutral not-available wording without a retry', async () => {
    getMock.mockRejectedValue(
      new ApiError({
        status: 404,
        code: 'not_found',
        message: 'Document not found',
      }),
    )
    renderDetail()

    await waitFor(() =>
      expect(screen.getByText(/not available/i)).toBeInTheDocument(),
    )
    expect(
      screen.queryByRole('button', { name: /retry/i }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('alpha.pdf')).not.toBeInTheDocument()
  })

  it('shows a retryable error for 5xx and recovers on retry', async () => {
    getMock
      .mockRejectedValueOnce(
        new ApiError({ status: 500, code: 'internal_error', message: 'Boom' }),
      )
      .mockResolvedValueOnce(INDEXED as never)
    renderDetail()

    await waitFor(() =>
      expect(screen.getByLabelText(/error/i)).toBeInTheDocument(),
    )
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'alpha.pdf' }),
      ).toBeInTheDocument(),
    )
    expect(getMock).toHaveBeenCalledTimes(2)
  })
})

describe('document detail route guard', () => {
  it('registers the protected $documentId route in the router', () => {
    expect(documentDetailRoute.options.path).toBe('/documents/$documentId')
    const byId = (router as unknown as { routesById?: Record<string, unknown> })
      .routesById
    expect(Object.keys(byId ?? {}).join('\n')).toContain('$documentId')
  })

  it('redirects anonymous visitors and allows authenticated sessions', () => {
    const beforeLoad = documentDetailRoute.options.beforeLoad as (
      // biome-ignore lint/suspicious/noExplicitAny: TanStack passes a full router context; the guard reads only the pathname.
      arg: any,
    ) => void
    expect(() =>
      beforeLoad({ location: { pathname: `/documents/${DOC_ID}` } }),
    ).toThrow()

    setSession({ authenticated: true })
    expect(() =>
      beforeLoad({ location: { pathname: `/documents/${DOC_ID}` } }),
    ).not.toThrow()
  })
})
