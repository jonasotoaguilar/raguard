import { queryOptions, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError } from '../api/client'
import {
  type DocumentList,
  listDocuments,
  uploadDocument,
} from '../api/documents'
import { EmptyState, ErrorState, ForbiddenState, Skeleton } from '../app/shell'
import { Dropzone } from '../components/Dropzone'
import { type ChipStatus, StatusChip } from '../components/StatusChip'

/** Sole data-layer key for the documents library. */
export const DOCUMENTS_QUERY_KEY = ['documents'] as const

/** Pending poll cadence: exactly 5s, only while work is in flight. */
export const DOCUMENTS_POLL_MS = 5000

/**
 * Poll while any returned document is still processing. `indexing` is not
 * returned by the API today but is tolerated for forward compatibility.
 */
export function documentsPollInterval(
  data: DocumentList | undefined,
): number | false {
  const docs = data?.documents ?? []
  const active = docs.some(
    (doc) => doc.status === 'pending' || (doc.status as string) === 'indexing',
  )
  return active ? DOCUMENTS_POLL_MS : false
}

/** Shared Query options: focus refetch on, background polling off. */
export function documentsQueryOptions() {
  return queryOptions({
    queryKey: DOCUMENTS_QUERY_KEY,
    queryFn: ({ signal }) => listDocuments({ signal }),
    refetchOnWindowFocus: true,
    refetchInterval: (query) => documentsPollInterval(query.state.data),
    refetchIntervalInBackground: false,
  })
}

/**
 * ODD-4 documents library. Member-protected by the route guard; tenant and
 * query state stay in component memory only. Uploads run sequentially
 * (bounded in-flight queue of one) and refresh the list on success without
 * losing already listed documents on failure.
 */
export function DocumentsPage() {
  const queryClient = useQueryClient()
  const documents = useQuery(documentsQueryOptions())
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  async function handleFiles(files: File[]) {
    if (uploading || files.length === 0) return
    setUploading(true)
    setUploadError(null)
    let succeeded = 0
    let failed = 0
    for (const file of files) {
      try {
        await uploadDocument(file)
        succeeded += 1
      } catch {
        failed += 1
      }
    }
    if (succeeded > 0) {
      await queryClient.invalidateQueries({
        queryKey: DOCUMENTS_QUERY_KEY,
      })
    }
    if (failed > 0) {
      setUploadError(
        succeeded > 0
          ? `Uploaded ${succeeded} of ${files.length} files. One file could not be added — the uploaded files are safe. Check the remaining file and try again.`
          : 'Upload failed. Nothing was added — check the file type and size, then try again.',
      )
    }
    setUploading(false)
  }

  const error = documents.error instanceof ApiError ? documents.error : null
  const docs = documents.data?.documents ?? []

  return (
    <section
      aria-labelledby="documents-title"
      style={{ maxWidth: 720, padding: 16 }}
    >
      <h1 id="documents-title">Documents</h1>
      <Dropzone
        onFiles={(files) => void handleFiles(files)}
        disabled={uploading}
      />
      {uploading ? <p role="status">Uploading…</p> : null}
      {uploadError ? <p role="alert">{uploadError}</p> : null}
      {documents.isPending ? <Skeleton label="Loading documents" /> : null}
      {documents.isError ? (
        error?.status === 403 ? (
          <ForbiddenState />
        ) : (
          <ErrorState
            code={error?.code ?? 'unknown_error'}
            message={error?.message ?? 'Request failed. Please try again.'}
            onRetry={() => void documents.refetch()}
          />
        )
      ) : null}
      {documents.isSuccess && docs.length === 0 ? (
        <EmptyState
          title="No documents yet"
          body="Upload a PDF or Markdown file above to get started."
        />
      ) : null}
      {documents.isSuccess && docs.length > 0 ? (
        <table style={{ width: '100%', marginTop: 16 }}>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((doc) => (
              <tr key={doc.id}>
                <td style={{ overflowWrap: 'anywhere' }}>
                  <a href={`/documents/${doc.id}`}>{doc.name}</a>
                </td>
                <td>
                  <StatusChip
                    status={doc.status as ChipStatus}
                    failureReason={doc.failure_reason}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  )
}
