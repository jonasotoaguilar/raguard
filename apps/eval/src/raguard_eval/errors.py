"""Eval dataset error contract: invalid datasets map to exit 3, no verdict."""

from __future__ import annotations

EXIT_DATASET_INVALID = 3


class DatasetInvalid(Exception):
    """Raised when dataset validation fails; the CLI maps this to exit 3."""

    exit_code = EXIT_DATASET_INVALID
