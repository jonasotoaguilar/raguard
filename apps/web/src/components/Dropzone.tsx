import {
  type ChangeEvent,
  type DragEvent,
  useId,
  useRef,
  useState,
} from 'react'
import { tokens } from '../app/shell'

/**
 * ODD-4 dropzone. Client-side pre-validation is UX only: it mirrors the
 * backend bound (20 MiB, `.pdf`/`.md`/`.markdown`, PDF-or-Markdown MIME) so
 * bad files fail fast with an actionable message, but the server re-validates
 * every upload. Rejected files never reach `onFiles`; valid files are kept.
 */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024
const ACCEPT = '.pdf,.md,.markdown,application/pdf,text/markdown'

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot).toLowerCase() : ''
}

/** Null when the file passes the client UX bound, else a human-readable why. */
function rejectionReason(file: File): string | null {
  if (!['.pdf', '.md', '.markdown'].includes(extensionOf(file.name))) {
    return 'unsupported file type — use .pdf, .md, or .markdown'
  }
  // Empty MIME is common for .md on some platforms: the extension governs
  // and the server decides. A non-empty unexpected MIME is rejected outright.
  if (
    file.type !== '' &&
    !['application/pdf', 'text/markdown'].includes(file.type)
  ) {
    return `unsupported format "${file.type}" — use PDF or Markdown files`
  }
  return file.size > MAX_UPLOAD_BYTES
    ? 'exceeds the 20 MiB per-file limit'
    : null
}

/** Visually hidden but screen-reader and keyboard reachable. */
const srOnly = {
  position: 'absolute' as const,
  width: 1,
  height: 1,
  overflow: 'hidden' as const,
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap' as const,
}

export function Dropzone({
  onFiles,
  disabled = false,
  id,
}: {
  onFiles: (files: File[]) => void
  disabled?: boolean
  id?: string
}) {
  const generated = useId()
  const inputId = id ?? `dropzone-input-${generated}`
  const errorId = `${inputId}-error`
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Single validation path shared by input selection and drag/drop.
  function handleBatch(files: File[]) {
    if (disabled || files.length === 0) return
    const valid: File[] = []
    const rejected: string[] = []
    for (const file of files) {
      const reason = rejectionReason(file)
      if (reason === null) valid.push(file)
      else rejected.push(`${file.name}: ${reason}`)
    }
    setError(
      rejected.length > 0
        ? `Some files were not added — ${rejected.join('; ')}. Fix them and try again; the server checks uploads again.`
        : null,
    )
    if (valid.length > 0) onFiles(valid)
  }

  function onInputChange(event: ChangeEvent<HTMLInputElement>) {
    handleBatch(Array.from(event.target.files ?? []))
    // Reset so re-selecting the same file fires change again. Programmatic
    // reset emits no event, so this cannot double-report a selection.
    event.target.value = ''
  }

  function onTargetDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault()
    setDragging(false)
    handleBatch(Array.from(event.dataTransfer.files ?? []))
  }

  return (
    <div style={{ maxWidth: '100%' }}>
      <button
        type="button"
        disabled={disabled}
        aria-label="Upload documents"
        aria-describedby={error ? errorId : undefined}
        data-testid="dropzone-target"
        onClick={() => {
          if (!disabled) inputRef.current?.click()
        }}
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onTargetDrop}
        style={{
          width: '100%',
          font: 'inherit',
          cursor: disabled ? 'not-allowed' : 'pointer',
          background: tokens.surfaceRaised,
          color: tokens.ink,
          border: `2px dashed ${dragging ? tokens.primary : tokens.border}`,
          borderRadius: 8,
          padding: '16px',
          textAlign: 'center',
          overflowWrap: 'anywhere',
        }}
      >
        <p style={{ margin: '0 0 4px' }}>
          Drag and drop .pdf, .md, or .markdown files here, or press Enter to
          browse
        </p>
        <p style={{ margin: 0, color: tokens.inkMuted }}>
          Up to 20 MiB per file. Files are checked here for speed and again on
          the server.
        </p>
      </button>
      {/* The visible target above forwards to this input; this sr-only label
          keeps the input really labelled without a second visible trigger
          that would double-fire selection events. */}
      <label htmlFor={inputId} style={srOnly}>
        Choose document files
      </label>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        multiple
        accept={ACCEPT}
        disabled={disabled}
        onChange={onInputChange}
        data-testid="dropzone-input"
        style={srOnly}
      />
      {error ? (
        <p
          id={errorId}
          role="alert"
          data-testid="dropzone-error"
          style={{
            color: tokens.danger,
            overflowWrap: 'anywhere',
            maxWidth: '100%',
          }}
        >
          {error}
        </p>
      ) : null}
    </div>
  )
}
