import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, clearSession, setSession } from '../api/client'
import {
  createGrant,
  deleteDocument,
  deleteGrant,
  getDocument,
  listGrants,
  updateDocumentVisibility,
} from '../api/documents'
import { documentDetailRoute, router } from '../app/router'
import { DocumentDetailPage, documentDetailQueryOptions } from './documents'

vi.mock('../api/documents', () => ({
  deleteDocument: vi.fn(),
  listDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  getDocument: vi.fn(),
  listGrants: vi.fn(),
  createGrant: vi.fn(),
  deleteGrant: vi.fn(),
  updateDocumentVisibility: vi.fn(),
  isDocumentVisibility: (value: unknown) =>
    value === 'tenant' || value === 'restricted',
}))

const deleteMock = vi.mocked(deleteDocument)
const getMock = vi.mocked(getDocument)
const listGrantsMock = vi.mocked(listGrants)
const createGrantMock = vi.mocked(createGrant)
const deleteGrantMock = vi.mocked(deleteGrant)
const updateVisibilityMock = vi.mocked(updateDocumentVisibility)

const DOC_ID = '11111111-1111-1111-1111-111111111111'

const INDEXED = {
  id: DOC_ID,
  name: 'alpha.pdf',
  status: 'indexed',
  failure_reason: null,
  visibility: 'tenant',
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
  listGrantsMock.mockResolvedValue({ grants: [] } as never)
})

afterEach(() => {
  cleanup()
  clearSession()
  vi.unstubAllGlobals()
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

describe('DocumentDetailPage delete', () => {
  it('deletes on confirm and calls the API with the document id', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    getMock.mockResolvedValue(INDEXED as never)
    deleteMock.mockResolvedValue(undefined as never)
    const user = userEvent.setup()
    renderDetail()

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /^delete$/i }),
      ).toBeInTheDocument(),
    )
    await user.click(screen.getByRole('button', { name: /^delete$/i }))

    await waitFor(() => expect(deleteMock).toHaveBeenCalledTimes(1))
    expect(deleteMock).toHaveBeenCalledWith(DOC_ID)
  })

  it('does nothing when the confirmation is dismissed', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false))
    getMock.mockResolvedValue(INDEXED as never)
    const user = userEvent.setup()
    renderDetail()

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /^delete$/i }),
      ).toBeInTheDocument(),
    )
    await user.click(screen.getByRole('button', { name: /^delete$/i }))

    expect(deleteMock).not.toHaveBeenCalled()
    expect(
      screen.getByRole('heading', { name: 'alpha.pdf' }),
    ).toBeInTheDocument()
  })

  it('surfaces a calm error when deletion fails', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    getMock.mockResolvedValue(INDEXED as never)
    deleteMock.mockRejectedValue(
      new ApiError({ status: 500, code: 'internal_error', message: 'Boom' }),
    )
    const user = userEvent.setup()
    renderDetail()

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /^delete$/i }),
      ).toBeInTheDocument(),
    )
    await user.click(screen.getByRole('button', { name: /^delete$/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent(/could not delete/i)
  })
})

describe('DocumentDetailPage visibility and grants', () => {
  it('saves a visibility change through the API', async () => {
    getMock.mockResolvedValue(INDEXED as never)
    updateVisibilityMock.mockResolvedValue({
      ...INDEXED,
      visibility: 'restricted',
    } as never)
    const user = userEvent.setup()
    renderDetail()

    await waitFor(() =>
      expect(screen.getByLabelText('Visibility')).toBeInTheDocument(),
    )
    await user.selectOptions(screen.getByLabelText('Visibility'), 'restricted')
    await user.click(screen.getByRole('button', { name: /save visibility/i }))

    await waitFor(() =>
      expect(updateVisibilityMock).toHaveBeenCalledWith(DOC_ID, 'restricted'),
    )
  })

  it('lists grants and adds one through the form', async () => {
    getMock.mockResolvedValue(INDEXED as never)
    listGrantsMock.mockResolvedValue({ grants: [] } as never)
    createGrantMock.mockResolvedValue({
      id: 'grant-1',
      grantee_type: 'user',
      grantee_id: '22222222-2222-2222-2222-222222222222',
    } as never)
    const user = userEvent.setup()
    renderDetail()

    await waitFor(() =>
      expect(screen.getByText('No grants yet.')).toBeInTheDocument(),
    )
    await user.type(
      screen.getByLabelText('Grantee ID'),
      '22222222-2222-2222-2222-222222222222',
    )
    await user.click(screen.getByRole('button', { name: /add grant/i }))

    await waitFor(() =>
      expect(createGrantMock).toHaveBeenCalledWith(DOC_ID, {
        grantee_type: 'user',
        grantee_id: '22222222-2222-2222-2222-222222222222',
      }),
    )
  })

  it('removes a grant through the API', async () => {
    getMock.mockResolvedValue(INDEXED as never)
    listGrantsMock.mockResolvedValue({
      grants: [
        {
          id: 'grant-1',
          grantee_type: 'role',
          grantee_id: '33333333-3333-3333-3333-333333333333',
        },
      ],
    } as never)
    deleteGrantMock.mockResolvedValue(undefined as never)
    const user = userEvent.setup()
    renderDetail()

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /delete grant grant-1/i }),
      ).toBeInTheDocument(),
    )
    await user.click(
      screen.getByRole('button', { name: /delete grant grant-1/i }),
    )

    await waitFor(() =>
      expect(deleteGrantMock).toHaveBeenCalledWith(DOC_ID, 'grant-1'),
    )
  })
})
