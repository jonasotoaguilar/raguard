"""Parameterized text chunking for the ingestion pipeline (task 4.3).

``chunk_text`` is a pure sliding-window chunker: fixed ``chunk_size`` windows
stepping by ``chunk_size - overlap`` so consecutive chunks share the overlap
as real content. The 10k-chunk design bound raises the typed
``ResourceLimitError`` so the job can end in the allowlisted ``limit`` reason.
``make_chunker`` closes the settings over the parameters for the ``ctx`` seam.
"""

from collections.abc import Callable

from raguard_worker.parsers import ResourceLimitError


def chunk_text(*, text: str, chunk_size: int, overlap: int, max_chunks: int) -> list[str]:
    """Split ``text`` into overlapping windows of ``chunk_size`` characters."""
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk bounds violated: require 0 <= overlap < chunk_size")
    step = chunk_size - overlap
    chunks = [text[start : start + chunk_size] for start in range(0, len(text), step)]
    chunks = [chunk for chunk in chunks if chunk]
    if len(chunks) > max_chunks:
        raise ResourceLimitError(f"chunk limit exceeded: {len(chunks)} > {max_chunks}")
    return chunks


def make_chunker(*, chunk_size: int, overlap: int, max_chunks: int) -> Callable[[str], list[str]]:
    """Build the chunker the job context expects, bound to fixed parameters."""
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk bounds violated: require 0 <= overlap < chunk_size")
    return lambda text: chunk_text(
        text=text, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks
    )
