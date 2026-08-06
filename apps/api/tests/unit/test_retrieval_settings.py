"""Unit tests for the bounded retrieval settings (task 1.3 RED).

The design fixes defaults (rrf_k=60, candidates=50, top_k=10, ef_search=100,
top_k_max=50, max query 2000 chars) and requires startup rejection of
inconsistent settings: any out-of-range value and any ef_search below the
candidate count must fail at instantiation, mirroring the worker's
validate_dispatch_bounds pattern.
"""

import pytest
from raguard_api.config import Settings

pytestmark = pytest.mark.unit

JWT_SECRET = "a" * 32


def _settings(**overrides) -> Settings:
    return Settings(jwt_secret=JWT_SECRET, **overrides)


def test_retrieval_defaults_match_design():
    settings = _settings()

    assert settings.rrf_k == 60
    assert settings.retrieval_candidates == 50
    assert settings.retrieval_top_k == 10
    assert settings.retrieval_top_k_max == 50
    assert settings.retrieval_ef_search == 100
    assert settings.retrieval_max_query_length == 2000
    assert settings.embedding_model == "text-embedding-3-small"


def test_retrieval_fields_are_environment_configurable(monkeypatch):
    monkeypatch.setenv("RRF_K", "42")
    monkeypatch.setenv("RETRIEVAL_EF_SEARCH", "120")

    settings = _settings()

    assert settings.rrf_k == 42
    assert settings.retrieval_ef_search == 120


def test_startup_rejects_ef_search_below_candidates():
    with pytest.raises(ValueError, match="ef_search"):
        _settings(retrieval_ef_search=10, retrieval_candidates=50)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rrf_k", 0),
        ("rrf_k", 1001),
        ("retrieval_candidates", 0),
        ("retrieval_candidates", 201),
        ("retrieval_top_k", 0),
        ("retrieval_top_k_max", 0),
        ("retrieval_top_k_max", 51),
        ("retrieval_ef_search", 0),
        ("retrieval_ef_search", 1001),
        ("retrieval_max_query_length", 0),
        ("retrieval_max_query_length", 10001),
    ],
)
def test_startup_rejects_out_of_range_values(field, value):
    with pytest.raises(ValueError):
        _settings(**{field: value})


def test_startup_rejects_top_k_above_configured_max():
    with pytest.raises(ValueError, match="retrieval_top_k"):
        _settings(retrieval_top_k=51, retrieval_top_k_max=50)


def test_top_k_at_configured_max_is_accepted():
    settings = _settings(retrieval_top_k=50, retrieval_top_k_max=50)

    assert settings.retrieval_top_k == 50
    assert settings.retrieval_top_k_max == 50
