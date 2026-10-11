/** ODD-4 documents API: tenant-scoped list/detail plus multipart upload. */
import { apiFetch } from './client'

export type DocumentStatus = 'pending' | 'indexed' | 'failed'

export type DocumentVisibility = 'tenant' | 'restricted'

export function isDocumentVisibility(
  value: unknown,
): value is DocumentVisibility {
  return value === 'tenant' || value === 'restricted'
}

export interface Document {
  id: string
  name: string
  status: DocumentStatus
  failure_reason: string | null
  visibility: DocumentVisibility
}

export type GranteeType = 'user' | 'role'

export interface DocumentGrant {
  id: string
  grantee_type: GranteeType
  grantee_id: string
}

export interface DocumentGrantList {
  grants: DocumentGrant[]
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

/** PATCH /api/documents/{id}/visibility: switch tenant/restricted (managers only). */
export function updateDocumentVisibility(
  id: string,
  visibility: DocumentVisibility,
  init: { signal?: AbortSignal } = {},
): Promise<Document> {
  return apiFetch<Document>(`${DOCUMENTS_API_PATH}/${id}/visibility`, {
    method: 'PATCH',
    body: JSON.stringify({ visibility }),
    signal: init.signal,
  })
}

/** GET /api/documents/{id}/grants: per-document grants (managers only). */
export function listGrants(
  id: string,
  init: { signal?: AbortSignal } = {},
): Promise<DocumentGrantList> {
  return apiFetch<DocumentGrantList>(`${DOCUMENTS_API_PATH}/${id}/grants`, {
    signal: init.signal,
  })
}

/** POST /api/documents/{id}/grants: grant a tenant user or role (managers only). */
export function createGrant(
  id: string,
  grant: { grantee_type: GranteeType; grantee_id: string },
  init: { signal?: AbortSignal } = {},
): Promise<DocumentGrant> {
  return apiFetch<DocumentGrant>(`${DOCUMENTS_API_PATH}/${id}/grants`, {
    method: 'POST',
    body: JSON.stringify(grant),
    signal: init.signal,
  })
}

/** DELETE /api/documents/{id}/grants/{grantId}: revoke one grant (managers only). */
export function deleteGrant(
  id: string,
  grantId: string,
  init: { signal?: AbortSignal } = {},
): Promise<void> {
  return apiFetch<void>(`${DOCUMENTS_API_PATH}/${id}/grants/${grantId}`, {
    method: 'DELETE',
    signal: init.signal,
  })
}

/** DELETE /api/documents/{id}: 204 with no body; cross-tenant is a neutral 404. */
export function deleteDocument(
  id: string,
  init: { signal?: AbortSignal } = {},
): Promise<void> {
  return apiFetch<void>(`${DOCUMENTS_API_PATH}/${id}`, {
    method: 'DELETE',
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
