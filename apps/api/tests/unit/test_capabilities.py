"""Unit tests: capability constants and the default admin/member matrix (task 3.1).

The capability tokens must match the roles.capabilities CHECK allowlist from
the identity migration; admin grants every declared capability, member grants
exactly corpus.view + chat.use, and unknown roles receive no default grants.
"""

import pytest
from raguard_api.authorization import capabilities
from raguard_api.identity.models import ALLOWED_CAPABILITIES

ALL_FIVE = {
    capabilities.ORG_SETTINGS_MANAGE,
    capabilities.USERS_MANAGE,
    capabilities.DOCUMENTS_MANAGE,
    capabilities.CORPUS_VIEW,
    capabilities.CHAT_USE,
}


def test_declared_capabilities_match_database_allowlist():
    assert capabilities.ALL_CAPABILITIES == frozenset(ALLOWED_CAPABILITIES)


def test_admin_capabilities_include_every_declared_capability():
    assert capabilities.ADMIN_CAPABILITIES == ALL_FIVE
    for capability in ALL_FIVE:
        assert capability in capabilities.ADMIN_CAPABILITIES


def test_member_capabilities_are_exactly_view_and_chat():
    assert capabilities.MEMBER_CAPABILITIES == {
        capabilities.CORPUS_VIEW,
        capabilities.CHAT_USE,
    }
    assert capabilities.USERS_MANAGE not in capabilities.MEMBER_CAPABILITIES
    assert capabilities.ORG_SETTINGS_MANAGE not in capabilities.MEMBER_CAPABILITIES
    assert capabilities.DOCUMENTS_MANAGE not in capabilities.MEMBER_CAPABILITIES


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("admin", ALL_FIVE),
        ("member", {capabilities.CORPUS_VIEW, capabilities.CHAT_USE}),
    ],
)
def test_default_role_capabilities(role, expected):
    assert capabilities.capabilities_for_role(role) == expected


def test_unknown_role_has_no_default_grants():
    assert capabilities.capabilities_for_role("editor") is None
