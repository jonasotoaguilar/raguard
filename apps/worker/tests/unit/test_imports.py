"""Worker -> API package boundary (task 1.1).

RED proof for the workspace packaging unit (PR 1): the worker must consume
the shared ``raguard_api`` package as an installed workspace dependency
(design decision: uv_build packages; no PYTHONPATH fragility).
"""

from importlib import metadata

import pytest

pytestmark = pytest.mark.unit


def test_raguard_api_is_installed_workspace_distribution() -> None:
    """The ``raguard-api`` distribution must be installed in the workspace venv."""
    assert metadata.version("raguard-api") == "0.1.0"


def test_worker_imports_shared_api_module() -> None:
    """The worker can import real API modules, not just the package name."""
    from raguard_api.config import Settings

    settings = Settings(jwt_secret="x" * 32)
    assert settings.jwt_issuer == "raguard"
