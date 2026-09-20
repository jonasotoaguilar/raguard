import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  DOCUMENTS_API_PATH,
  getDocument,
  listDocuments,
  uploadDocument,
} from './documents'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.unstubAllGlobals()
})

describe('listDocuments', () => {
  it('GETs /api/documents and mirrors the document envelope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        documents: [
          {
            id: '11111111-1111-1111-1111-111111111111',
            name: 'alpha.pdf',
            status: 'indexed',
            failure_reason: null,
          },
          {
            id: '22222222-2222-2222-2222-222222222222',
            name: 'beta.md',
            status: 'failed',
            failure_reason: 'malformed',
          },
        ],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await listDocuments()

    expect(fetchMock).toHaveBeenCalledWith(
      DOCUMENTS_API_PATH,
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(fetchMock.mock.calls[0][1].method ?? 'GET').toBe('GET')
    expect(result.documents).toHaveLength(2)
    expect(result.documents[0]).toEqual({
      id: '11111111-1111-1111-1111-111111111111',
      name: 'alpha.pdf',
      status: 'indexed',
      failure_reason: null,
    })
  })

  it('forwards an abort signal', async () => {
    const controller = new AbortController()
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { documents: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await listDocuments({ signal: controller.signal })

    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('propagates a 403 ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(403, {
          error: { code: 'forbidden', message: 'Nope' },
        }),
      ),
    )
    await expect(listDocuments()).rejects.toMatchObject({
      status: 403,
      code: 'forbidden',
    })
  })
})

describe('getDocument', () => {
  it('GETs /api/documents/{id} and mirrors one envelope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        id: '11111111-1111-1111-1111-111111111111',
        name: 'alpha.pdf',
        status: 'pending',
        failure_reason: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await getDocument('11111111-1111-1111-1111-111111111111')

    expect(fetchMock).toHaveBeenCalledWith(
      `${DOCUMENTS_API_PATH}/11111111-1111-1111-1111-111111111111`,
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(result).toEqual({
      id: '11111111-1111-1111-1111-111111111111',
      name: 'alpha.pdf',
      status: 'pending',
      failure_reason: null,
    })
  })

  it('forwards an abort signal', async () => {
    const controller = new AbortController()
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        id: 'x',
        name: 'a.pdf',
        status: 'pending',
        failure_reason: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await getDocument('x', { signal: controller.signal })

    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('propagates a neutral 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(404, {
          error: { code: 'not_found', message: 'Document not found' },
        }),
      ),
    )
    await expect(getDocument('missing')).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
    })
  })
})

describe('uploadDocument', () => {
  it('POSTs multipart FormData with the file field and mirrors the created document', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(201, {
        id: '33333333-3333-3333-3333-333333333333',
        name: 'upload.pdf',
        status: 'pending',
        failure_reason: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['%PDF-1.4 body'], 'upload.pdf', {
      type: 'application/pdf',
    })

    const result = await uploadDocument(file)

    expect(fetchMock).toHaveBeenCalledWith(
      DOCUMENTS_API_PATH,
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
    const body = fetchMock.mock.calls[0][1].body
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file')).toBeInstanceOf(File)
    expect((body.get('file') as File).name).toBe('upload.pdf')
    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers['content-type']).toBeUndefined()
    expect(result).toEqual({
      id: '33333333-3333-3333-3333-333333333333',
      name: 'upload.pdf',
      status: 'pending',
      failure_reason: null,
    })
  })

  it('forwards an abort signal on upload', async () => {
    const controller = new AbortController()
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(201, {
        id: 'x',
        name: 'a.pdf',
        status: 'pending',
        failure_reason: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['body'], 'a.pdf', { type: 'application/pdf' })

    await uploadDocument(file, { signal: controller.signal })

    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('propagates a 400 validation error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(400, {
          error: { code: 'invalid_request', message: 'Unsupported file type' },
        }),
      ),
    )
    const file = new File(['x'], 'evil.exe', { type: 'application/pdf' })
    await expect(uploadDocument(file)).rejects.toMatchObject({
      status: 400,
      code: 'invalid_request',
    })
  })
})
