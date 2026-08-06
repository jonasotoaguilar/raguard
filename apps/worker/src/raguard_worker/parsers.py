"""PDF/Markdown parsing behind the shared Parser protocol (task 4.3).

``PdfMarkdownParser`` sniffs the PDF magic bytes and either parses with pypdf
or decodes UTF-8 text (Markdown is content, not markup, so it passes through
verbatim). Resource bounds are enforced before any extraction work: the page
count bound is checked first, then the accumulated character bound while
extracting. The typed errors here are the pipeline's failure vocabulary —
``jobs.py`` maps them to the allowlisted terminal reasons (encrypted/limit/
malformed) via ``parse_failure_reason``. Content is always treated as inert
data; nothing is ever executed or interpreted.
"""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError


class ParsingError(Exception):
    """Base class for typed content-processing failures."""


class MalformedDocumentError(ParsingError):
    """The bytes are not a parsable PDF or valid UTF-8 text."""


class EncryptedDocumentError(ParsingError):
    """The PDF is encrypted and cannot be read without a password."""


class ResourceLimitError(ParsingError):
    """A configured resource bound (pages, characters, chunks) was exceeded."""


def parse_failure_reason(exc: Exception) -> str:
    """Map a parser/chunker failure to its allowlisted terminal reason.

    DESIGN.md vocabulary: encrypted PDFs surface ``encrypted``, resource
    bounds surface ``limit``, everything else is ``malformed``.
    """
    if isinstance(exc, EncryptedDocumentError):
        return "encrypted"
    if isinstance(exc, ResourceLimitError):
        return "limit"
    return "malformed"


class PdfMarkdownParser:
    """Parser protocol implementation: pypdf for PDFs, UTF-8 decode otherwise.

    ``parse`` never raises raw pypdf errors: they are wrapped into the typed
    pipeline errors so the job can map them to allowlisted reasons.
    """

    def __init__(self, *, max_pages: int, max_characters: int) -> None:
        if max_pages < 1 or max_characters < 1:
            raise ValueError(
                "parser bounds violated: require max_pages >= 1 and max_characters >= 1"
            )
        self._max_pages = max_pages
        self._max_characters = max_characters

    def parse(self, data: bytes) -> str:
        if data.startswith(b"%PDF-"):
            return self._parse_pdf(data)
        return self._parse_text(data)

    def _parse_pdf(self, data: bytes) -> str:
        try:
            reader = PdfReader(BytesIO(data))
            page_count = len(reader.pages)
        except FileNotDecryptedError as exc:
            raise EncryptedDocumentError("PDF is encrypted") from exc
        except PdfReadError as exc:
            raise MalformedDocumentError("PDF could not be read") from exc
        if page_count > self._max_pages:
            raise ResourceLimitError(f"page limit exceeded: {page_count} > {self._max_pages}")
        pages: list[str] = []
        total = 0
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except PdfReadError as exc:
                raise MalformedDocumentError("PDF page could not be extracted") from exc
            total += len(text)
            if total > self._max_characters:
                raise ResourceLimitError(
                    f"character limit exceeded: {total} > {self._max_characters}"
                )
            pages.append(text)
        return "\n".join(pages)

    def _parse_text(self, data: bytes) -> str:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MalformedDocumentError("content is not valid UTF-8 text") from exc
        if len(text) > self._max_characters:
            raise ResourceLimitError(
                f"character limit exceeded: {len(text)} > {self._max_characters}"
            )
        return text
