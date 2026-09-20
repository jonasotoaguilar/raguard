/** ODD-4 documents API: tenant-scoped list/detail plus multipart upload. */
import { apiFetch } from './client'

export type DocumentStatus = 'pending' | 'indexed' | 'failed'

export interface Document {
  id: string
  name: string
  status: DocumentStatus
  failure_reason: string | null
}

export interface DocumentList {
  documents: Document[]
}

export const DOCUMENTS_API_PATH = '/api/documents'

/** GET /api/documents: tenant-scoped list; backend returns `{documents: [...]}`. */
export function listDocuments(
  init: { signal?: AbortSignal } = {},
): Promise<DocumentList> {
  return apiFetch<DocumentList>(DOCUMENTS_API_PATH, {
    signal: init.signal,
  })
}

/** GET /api/documents/{id}: one allowlisted envelope; cross-tenant is a neutral 404. */
export function getDocument(
  id: string,
  init: { signal?: AbortSignal } = {},
): Promise<Document> {
  return apiFetch<Document>(`${DOCUMENTS_API_PATH}/${id}`, {
    signal: init.signal,
  })
}

/** POST /api/documents: multipart `file` field; browser owns the boundary header. */
export function uploadDocument(
  file: File,
  init: { signal?: AbortSignal } = {},
): Promise<Document> {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<Document>(DOCUMENTS_API_PATH, {
    method: 'POST',
    body: form,
    signal: init.signal,
  })
}
