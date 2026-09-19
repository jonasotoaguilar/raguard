"""Tests for the Phase 4 evaluation CLI (task 4.1, RED).

Injectable ``main(argv, evaluator=...)``; no ``--live``; opt-in
``--fail-under-precision``; exits 0/2/3/1; JSON config precedence; atomic
report write with temp cleanup on failure.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from raguard_eval.cli import main

KINDS = ["relevant", "neutral", "cross-tenant", "capability-denied", "adversarial"]


def _write_dataset(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "dataset_id": "mvp-v1", "draft_precision_at_10": 0.70})
    )
    (root / "corpus.json").write_text(
        json.dumps(
            {
                "tenants": [{"id": "t-a"}, {"id": "t-b"}],
                "documents": [
                    {"id": "d-1", "tenant_id": "t-a"},
                    {"id": "d-2", "tenant_id": "t-b"},
                ],
                "chunks": [
                    {"id": "c-1", "tenant_id": "t-a", "document_id": "d-1", "content": "alpha"},
                    {"id": "c-3", "tenant_id": "t-b", "document_id": "d-2", "content": "echo"},
                ],
            }
        )
    )
    (root / "actors.json").write_text(
        json.dumps(
            {
                "actors": [
                    {"id": "actor-a", "tenant_id": "t-a", "capabilities": ["chat.use"]},
                    {"id": "actor-b", "tenant_id": "t-b", "capabilities": []},
                ]
            }
        )
    )
    rows = []
    for kind in KINDS:
        rel = {"relevant": ["c-1"], "adversarial": ["c-1"], "cross-tenant": ["c-3"]}.get(kind, [])
        rows.append(
            {
                "id": f"case-{kind}",
                "kind": kind,
                "actor_id": "actor-b" if kind == "capability-denied" else "actor-a",
                "query": f"query for {kind}",
                "relevant_chunk_ids": rel,
            }
        )
    (root / "cases.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return root


def _pass_evaluator(dataset: Any, *, k: int) -> dict[str, Any]:
    assert k > 0
    return {
        "aggregates": {"precision_at_10": 0.82},
        "cases": [{"id": "b"}, {"id": "a"}],
        "failure_reasons": [],
        "verdict": "pass",
    }


def _args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--dataset",
        str(tmp_path / "ds"),
        "--config",
        str(tmp_path / "config.json"),
        "--output",
        str(tmp_path / "reports" / "latest.json"),
        *extra,
    ]


@pytest.fixture()
def ready(tmp_path: Path) -> Path:
    _write_dataset(tmp_path / "ds")
    (tmp_path / "config.json").write_text(json.dumps({"k": 10, "draft_precision_at_10": 0.70}))
    return tmp_path


def test_help_and_no_live_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--dataset" in out
    assert "--live" not in out
    with pytest.raises(SystemExit) as rejected:
        main(["--live"])
    assert rejected.value.code != 0


def test_pass_report_exit_zero(ready: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(_args(ready), evaluator=_pass_evaluator) == 0
    report = json.loads((ready / "reports" / "latest.json").read_text())
    assert report["verdict"] == "pass"
    assert report["failure_reasons"] == []
    assert [c["id"] for c in report["cases"]] == ["a", "b"]
    assert "pass" in capsys.readouterr().out


def test_invariant_failure_exit_two(ready: Path) -> None:
    def evaluator(dataset: Any, *, k: int) -> dict[str, Any]:
        return {
            "aggregates": {},
            "cases": [],
            "failure_reasons": ["tenant_leak"],
            "verdict": "fail",
        }

    assert main(_args(ready), evaluator=evaluator) == 2
    report = json.loads((ready / "reports" / "latest.json").read_text())
    assert report["verdict"] == "fail"
    assert report["failure_reasons"] == ["tenant_leak"]


def test_precision_gate_opt_in(ready: Path) -> None:
    def evaluator(dataset: Any, *, k: int) -> dict[str, Any]:
        return {
            "aggregates": {"precision_at_10": 0.5},
            "cases": [],
            "failure_reasons": [],
            "verdict": "pass",
        }

    assert main(_args(ready), evaluator=evaluator) == 0
    assert main(_args(ready, "--fail-under-precision", "0.70"), evaluator=evaluator) == 2
    report = json.loads((ready / "reports" / "latest.json").read_text())
    assert report["verdict"] == "fail"
    assert report["failure_reasons"] == ["precision_below_threshold"]


def test_precision_gate_satisfied(ready: Path) -> None:
    assert main(_args(ready, "--fail-under-precision", "0.70"), evaluator=_pass_evaluator) == 0


def test_dataset_invalid_exit_three_no_report(tmp_path: Path) -> None:
    (tmp_path / "ds").mkdir()
    (tmp_path / "config.json").write_text(json.dumps({"k": 10}))
    output = tmp_path / "reports" / "latest.json"
    assert main(_args(tmp_path), evaluator=_pass_evaluator) == 3
    assert not output.exists()


def test_invalid_config_exit_three(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "ds")
    (tmp_path / "config.json").write_text("{not json")
    assert main(_args(tmp_path), evaluator=_pass_evaluator) == 3


def test_k_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_dataset(tmp_path / "ds")
    (tmp_path / "config.json").write_text(json.dumps({"k": 5}))
    seen: list[int] = []

    def evaluator(dataset: Any, *, k: int) -> dict[str, Any]:
        seen.append(k)
        return {"aggregates": {}, "cases": [], "failure_reasons": [], "verdict": "pass"}

    assert main(_args(tmp_path), evaluator=evaluator) == 0
    assert seen == [5]
    assert main(_args(tmp_path, "--k", "7"), evaluator=evaluator) == 0
    assert seen == [5, 7]
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "reports" / "latest.json"
    assert main(["--dataset", "ds", "--output", str(output)], evaluator=evaluator) == 0
    assert seen == [5, 7, 10]


def test_atomic_write_failure_cleanup(ready: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk fault")

    monkeypatch.setattr(os, "replace", boom)
    assert main(_args(ready), evaluator=_pass_evaluator) == 1
    leftovers = list((ready / "reports").glob("*.tmp*"))
    assert leftovers == []
    assert not (ready / "reports" / "latest.json").exists()


def test_evaluator_error_exit_one(ready: Path) -> None:
    def evaluator(dataset: Any, *, k: int) -> dict[str, Any]:
        raise RuntimeError("runner fault")

    assert main(_args(ready), evaluator=evaluator) == 1
    assert not (ready / "reports" / "latest.json").exists()


def test_invalid_k_exit_three(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "ds")
    (tmp_path / "config.json").write_text(json.dumps({"k": "ten"}))
    assert main(_args(tmp_path), evaluator=_pass_evaluator) == 3
    assert main(_args(tmp_path, "--k", "0"), evaluator=_pass_evaluator) == 3


def test_project_scripts_exposes_raguard_eval() -> None:
    root = Path(__file__).resolve().parents[4]
    text = (root / "apps" / "eval" / "pyproject.toml").read_text()
    assert "[project.scripts]" in text
    assert "raguard-eval" in text
    assert "raguard_eval.cli:main" in text


def test_default_evaluator_delegates_to_phase6_runner(
    ready: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import raguard_eval.cli as cli_module
    import raguard_eval.runner as runner_module

    called: dict[str, Any] = {}

    def fake_evaluate(dataset_dir: Any, *, k: int) -> dict[str, Any]:
        called["dataset_dir"] = str(dataset_dir)
        called["k"] = k
        return {
            "aggregates": {"precision_at_10": 0.9},
            "cases": [],
            "failure_reasons": [],
            "verdict": "pass",
        }

    monkeypatch.setattr(runner_module, "evaluate", fake_evaluate)
    result = cli_module._default_evaluate(str(ready / "ds"), k=10)
    assert called == {"dataset_dir": str(ready / "ds"), "k": 10}
    assert result["aggregates"] == {"precision_at_10": 0.9}


def test_main_uses_runner_by_default(ready: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import raguard_eval.runner as runner_module

    def fake_evaluate(dataset_dir: Any, *, k: int) -> dict[str, Any]:
        assert str(dataset_dir) == str(ready / "ds")
        assert k == 10
        return {
            "aggregates": {"precision_at_10": 0.9},
            "cases": [],
            "failure_reasons": [],
            "verdict": "pass",
        }

    monkeypatch.setattr(runner_module, "evaluate", fake_evaluate)
    assert main(_args(ready)) == 0
    report = json.loads((ready / "reports" / "latest.json").read_text())
    assert report["aggregates"] == {"precision_at_10": 0.9}
