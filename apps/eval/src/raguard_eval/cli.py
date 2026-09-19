"""Offline evaluation CLI: deterministic JSON report with distinct exits.

Exits: 0 pass, 2 invariant or opted-in precision gate, 3 dataset/config
error with no verdict, 1 internal or non-atomic write. No live-provider
flag; the default evaluator is the Phase 6 offline runner, while callers
may still inject a custom ``evaluator``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from raguard_eval.dataset import load_dataset
from raguard_eval.errors import DatasetInvalid
from raguard_eval.report import build_report

DEFAULT_K = 10
DEFAULT_CONFIG_PATH = "eval/config.json"
EXIT_PASS = 0
EXIT_INVARIANT = 2
EXIT_INTERNAL = 1

Evaluator = Callable[..., Mapping[str, Any]]


def _default_evaluate(dataset_dir: str | Path, *, k: int) -> Mapping[str, Any]:
    """Phase 6 offline runner over the CLI dataset directory."""
    from raguard_eval import runner as runner_module

    return runner_module.evaluate(dataset_dir, k=k)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="raguard-eval",
        description="Offline evaluation harness: validate a dataset and write a report.",
    )
    parser.add_argument("--dataset", default="eval/datasets/mvp-v1")
    parser.add_argument("--config", default=None)
    parser.add_argument("--output", default="eval/reports/latest.json")
    parser.add_argument("--k", type=int, default=None)
    parser.add_argument("--fail-under-precision", type=float, default=None)
    return parser.parse_args(argv)


def _load_config(explicit: str | None) -> dict[str, Any]:
    if explicit is None:
        default = Path(DEFAULT_CONFIG_PATH)
        if not default.exists():
            return {}
        explicit = DEFAULT_CONFIG_PATH
    try:
        raw = Path(explicit).read_text(encoding="utf-8")
    except OSError as exc:
        raise DatasetInvalid(f"cannot read config: {explicit}") from exc
    try:
        config = json.loads(raw)
    except ValueError as exc:
        raise DatasetInvalid(f"config is not valid JSON: {explicit}") from exc
    if not isinstance(config, dict):
        raise DatasetInvalid(f"config must be a JSON object: {explicit}")
    return config


def _as_number_or_none(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DatasetInvalid(f"config {name} must be numeric")
    return float(value)


def _apply_precision_gate(result: dict[str, Any], gate: float | None) -> dict[str, Any]:
    if gate is None:
        return result
    precision = result.get("aggregates", {}).get("precision_at_10")
    if isinstance(precision, bool) or not isinstance(precision, (int, float)):
        below = True
    else:
        below = precision < gate
    if not below:
        return result
    reasons = list(result.get("failure_reasons", []))
    if "precision_below_threshold" not in reasons:
        reasons.append("precision_below_threshold")
    return {**result, "failure_reasons": reasons, "verdict": "fail"}


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _atomic_write_text(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), prefix=f"{dest.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, dest)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    _fsync_dir(dest.parent)


def main(argv: Sequence[str] | None = None, evaluator: Evaluator | None = None) -> int:
    args = _parse_args(argv)
    try:
        config = _load_config(args.config)
        k = args.k if args.k is not None else config.get("k", DEFAULT_K)
        if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
            raise DatasetInvalid("k must be a positive int")
        gate = args.fail_under_precision
        if gate is None:
            gate = _as_number_or_none(config.get("fail_under_precision"), "fail_under_precision")
        draft = _as_number_or_none(config.get("draft_precision_at_10"), "draft_precision_at_10")
        dataset = load_dataset(args.dataset)
        if evaluator is None:
            evaluated = _default_evaluate(args.dataset, k=k)
        else:
            evaluated = evaluator(dataset, k=k)
        result = _apply_precision_gate(dict(evaluated), gate)
        settings: dict[str, Any] = {"k": k}
        for key in (
            "rrf_k",
            "retrieval_candidates",
            "retrieval_ef_search",
            "retrieval_semantic_max_distance",
        ):
            if config.get(key) is not None:
                settings[key] = config[key]
        report = build_report(
            dataset_id=dataset.dataset_id,
            dataset_sha256=dataset.dataset_sha256,
            settings=settings,
            thresholds={"draft_precision_at_10": draft, "fail_under_precision": gate},
            aggregates=result["aggregates"],
            cases=result["cases"],
            failure_reasons=result["failure_reasons"],
            verdict=result["verdict"],
        )
        _atomic_write_text(Path(args.output), json.dumps(report, indent=2, sort_keys=True) + "\n")
    except DatasetInvalid as exc:
        print(f"raguard-eval: dataset error: {exc}", file=sys.stderr)
        return DatasetInvalid.exit_code
    except Exception as exc:  # noqa: BLE001 — CLI boundary maps internals to exit 1
        print(f"raguard-eval: internal error: {exc}", file=sys.stderr)
        return EXIT_INTERNAL
    if report["verdict"] != "pass" or report["failure_reasons"]:
        print(
            f"verdict={report['verdict']} "
            f"failures={','.join(report['failure_reasons'])} "
            f"output={args.output}"
        )
        return EXIT_INVARIANT
    print(f"verdict=pass output={args.output}")
    return EXIT_PASS
