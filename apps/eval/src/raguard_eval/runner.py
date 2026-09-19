"""Offline deterministic per-case evaluation runner (ODD-1 / task 6.1).

Runs every case of a validated dataset against a disposable migrated
database through the production seams -- ``retrieve_chunks``,
``build_completion_prompt``/``SYSTEM_PROMPT``/``UNTRUSTED_SOURCES_*``,
``verify_citations``, ``FakeCompleter``, ``Settings`` -- with the
deterministic offline ``Sha256TokenEmbedder``. Fully offline: no external
model imports, clients, keys, or network calls.

Per case (id order): build a fresh ``AuthorizationScope``; snapshot
embedder/completer counts; actors without ``chat.use`` skip retrieval,
prompt construction, and completion entirely (unauthorized iff either
delta is greater than zero). Authorized cases flow through
retrieve -> prompt -> complete -> verify, then leak/boundary/citation
gates and relevant-only metrics. Any invariant breach fails the run.
Results carry synthetic ids and counts only -- never credentials,
emails, models, or raw embeddings.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from raguard_api.authorization.capabilities import CHAT_USE
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.chat.citations import CitationVerificationError, verify_citations
from raguard_api.chat.contracts import CompletionPrompt, FakeCompleter
from raguard_api.chat.prompts import (
    SYSTEM_PROMPT,
    UNTRUSTED_SOURCES_END,
    UNTRUSTED_SOURCES_START,
    build_completion_prompt,
)
from raguard_api.config import Settings
from raguard_api.documents.contracts import Embedder
from raguard_api.retrieval.contracts import FusedResult
from raguard_api.retrieval.service import retrieve_chunks
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_eval import metrics as eval_metrics
from raguard_eval.dataset import Case, Dataset, load_dataset
from raguard_eval.db import evaluation_database
from raguard_eval.embedder import Sha256TokenEmbedder
from raguard_eval.seed import SeededEvaluationData, seed_evaluation_database

DUMMY_JWT_SECRET = "eval-offline-dummy-secret-00000000"

_BRACKET_SPAN_RE = re.compile(r"\[[^\[\]\n]*\]")
_CITATION_LIKE_RE = re.compile(r"\[\s*-?\d[\d,\s\-]*\]")


class CountingEmbedder:
    """Offline embedder seam recording every call for per-case denial deltas."""

    def __init__(self, inner: Embedder | None = None) -> None:
        self._inner = inner or Sha256TokenEmbedder()
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Record the call, then delegate to the deterministic offline embedder."""
        self.calls.append(list(texts))
        return self._inner.embed(texts)


@dataclass
class _RunContext:
    dataset: Dataset
    seeded: SeededEvaluationData
    reverse_chunks: dict[uuid.UUID, str]
    session_factory: async_sessionmaker[AsyncSession]
    settings: Settings
    embedder: CountingEmbedder
    completer: FakeCompleter
    k: int


def _scope_for(dataset: Dataset, seeded: SeededEvaluationData, case: Case) -> AuthorizationScope:
    """Fresh tenant-leading scope for one case from the current seed mappings."""
    return AuthorizationScope(
        tenant_id=seeded.tenant_ids[dataset.actor_tenant[case.actor_id]],
        user_id=seeded.actor_user_ids[case.actor_id],
        capabilities=dataset.actor_capabilities[case.actor_id],
    )


def _serialized_sources(retrieved: Sequence[FusedResult]) -> str:
    """Rebuild the exact source JSON the production prompt must contain."""
    sources = [
        {
            "index": index,
            "chunk_id": str(chunk.chunk_id),
            "document_id": str(chunk.document_id),
            "document_name": chunk.document_name,
            "position": chunk.position,
            "content": chunk.content,
        }
        for index, chunk in enumerate(retrieved, start=1)
    ]
    return json.dumps(sources)


def _prompt_boundary_ok(prompt: CompletionPrompt, retrieved: Sequence[FusedResult]) -> bool:
    """System byte-equal; outermost START before later END; sources between them."""
    if prompt.system_prompt != SYSTEM_PROMPT:
        return False
    start = prompt.user_prompt.find(UNTRUSTED_SOURCES_START)
    end = prompt.user_prompt.rfind(UNTRUSTED_SOURCES_END)
    if start == -1 or end == -1 or not start < end:
        return False
    inner = prompt.user_prompt[start + len(UNTRUSTED_SOURCES_START) : end]
    return _serialized_sources(retrieved) in inner


def _has_malformed_attempt(completion: str, retrieved_count: int) -> bool:
    """A citation-like span that is not an exact valid marker was accepted."""
    valid = {f"[{index}]" for index in range(1, retrieved_count + 1)}
    for span in _BRACKET_SPAN_RE.findall(completion):
        if span in valid:
            continue
        if _CITATION_LIKE_RE.fullmatch(span):
            return True
    return False


def _citation_gate(
    completion: str, retrieved: Sequence[FusedResult]
) -> tuple[list[Any], str | None]:
    """Verify markers against the retrieved set; malformed acceptance is separate."""
    try:
        citations = verify_citations(completion, retrieved)
    except CitationVerificationError:
        return [], "citation_out_of_set"
    if _has_malformed_attempt(completion, len(retrieved)):
        return citations, "malformed_citation_accepted"
    return citations, None


def _denied_result(case: Case, top_k: int, embed_delta: int, complete_delta: int) -> dict[str, Any]:
    """Denied actors record deltas only; retrieval, prompt, and completion ran never."""
    return {
        "id": case.id,
        "kind": case.kind,
        "actor_id": case.actor_id,
        "top_k": top_k,
        "retrieved_chunk_ids": [],
        "embedder_calls": embed_delta,
        "completer_calls": complete_delta,
        "precision_at_k": None,
        "recall_at_k": None,
        "hit_rate_at_k": None,
        "neutral_fidelity": None,
        "citation_validity": None,
        "citation_count": 0,
    }


async def _evaluate_case(ctx: _RunContext, case: Case) -> tuple[dict[str, Any], set[str]]:
    """Evaluate one case; return its sanitized result plus its failure reasons."""
    scope = _scope_for(ctx.dataset, ctx.seeded, case)
    embed_before = len(ctx.embedder.calls)
    complete_before = len(ctx.completer.calls)
    top_k = case.top_k or ctx.k

    if not scope.has_capability(CHAT_USE):
        embed_delta = len(ctx.embedder.calls) - embed_before
        complete_delta = len(ctx.completer.calls) - complete_before
        reasons = {"unauthorized_execution"} if embed_delta > 0 or complete_delta > 0 else set()
        return _denied_result(case, top_k, embed_delta, complete_delta), reasons

    retrieved = await retrieve_chunks(
        ctx.session_factory, scope, ctx.settings, ctx.embedder, case.query, top_k=top_k
    )
    actor_tenant = ctx.dataset.actor_tenant[case.actor_id]
    retrieved_ids = [ctx.reverse_chunks.get(chunk.chunk_id, "") for chunk in retrieved]
    leak = any(
        not external_id or ctx.dataset.chunk_tenant.get(external_id) != actor_tenant
        for external_id in retrieved_ids
    )
    prompt = build_completion_prompt(case.query, retrieved)
    boundary_ok = _prompt_boundary_ok(prompt, retrieved)
    ctx.completer.text = case.completion_text or ("[1]" if retrieved else "")
    completion = await asyncio.to_thread(ctx.completer.complete, prompt)
    citations, citation_reason = _citation_gate(completion, retrieved)

    if case.kind == "relevant":
        precision = eval_metrics.precision_at_k(retrieved_ids, list(case.relevant_chunk_ids))
        recall = eval_metrics.recall_at_k(retrieved_ids, list(case.relevant_chunk_ids))
        hit = eval_metrics.hit_rate_at_k(retrieved_ids, list(case.relevant_chunk_ids))
        fidelity = None
    elif case.kind == "neutral":
        precision = recall = hit = None
        fidelity = eval_metrics.neutral_fidelity(retrieved_ids)
    else:
        precision = recall = hit = fidelity = None
    validity = eval_metrics.citation_validity(completion, len(retrieved))

    reasons = set()
    if leak:
        reasons.add("tenant_leak")
    if not boundary_ok:
        reasons.add("prompt_boundary_violation")
    if citation_reason is not None:
        reasons.add(citation_reason)
    return {
        "id": case.id,
        "kind": case.kind,
        "actor_id": case.actor_id,
        "top_k": top_k,
        "retrieved_chunk_ids": retrieved_ids,
        "embedder_calls": len(ctx.embedder.calls) - embed_before,
        "completer_calls": len(ctx.completer.calls) - complete_before,
        "precision_at_k": precision,
        "recall_at_k": recall,
        "hit_rate_at_k": hit,
        "neutral_fidelity": fidelity,
        "citation_validity": validity,
        "citation_count": len(citations),
    }, reasons


def _default_settings() -> Settings:
    """Production settings with a dummy secret that is never reported."""
    return Settings(jwt_secret=DUMMY_JWT_SECRET)


async def run_evaluation(
    dataset_dir: str | Path, *, k: int = 10, settings: Settings | None = None
) -> dict[str, Any]:
    """Seed a disposable database and evaluate every case in id order."""
    root = Path(dataset_dir)
    dataset = load_dataset(root)
    active = settings or _default_settings()
    ctx_embedder = CountingEmbedder()
    ctx_completer = FakeCompleter("")
    records: list[tuple[dict[str, Any], set[str]]] = []
    async with evaluation_database() as db:
        seeded = await seed_evaluation_database(db.session_factory, root)
        ctx = _RunContext(
            dataset=dataset,
            seeded=seeded,
            reverse_chunks={
                row_id: external_id for external_id, row_id in seeded.chunk_ids.items()
            },
            session_factory=db.session_factory,
            settings=active,
            embedder=ctx_embedder,
            completer=ctx_completer,
            k=k,
        )
        for case in sorted(dataset.cases, key=lambda item: item.id):
            records.append(await _evaluate_case(ctx, case))
    relevant = [result for result, _ in records if result["kind"] == "relevant"]
    neutral = [result for result, _ in records if result["kind"] == "neutral"]
    aggregates = {
        "precision_at_k": eval_metrics.mean_or_none(
            [result["precision_at_k"] for result in relevant]
        ),
        "recall_at_k": eval_metrics.mean_or_none([result["recall_at_k"] for result in relevant]),
        "hit_rate_at_k": eval_metrics.mean_or_none(
            [result["hit_rate_at_k"] for result in relevant]
        ),
        "neutral_fidelity": eval_metrics.mean_or_none(
            [result["neutral_fidelity"] for result in neutral]
        ),
        "citation_validity": eval_metrics.mean_or_none(
            [result["citation_validity"] for result, _ in records]
        ),
        "honest_empty_citations": sum(
            1
            for result, reasons in records
            if not reasons
            and result["kind"] != "capability-denied"
            and result["citation_validity"] is None
            and result["citation_count"] == 0
        ),
        "case_count": len(records),
    }
    failure_reasons = sorted({reason for _, reasons in records for reason in reasons})
    return {
        "aggregates": aggregates,
        "cases": [result for result, _ in records],
        "failure_reasons": failure_reasons,
        "verdict": "fail" if failure_reasons else "pass",
    }


def evaluate(
    dataset_dir: str | Path, *, k: int = 10, settings: Settings | None = None
) -> dict[str, Any]:
    """Synchronous entry for CLI-style callers; ODD-2 wires the default evaluator."""
    return asyncio.run(run_evaluation(dataset_dir, k=k, settings=settings))
