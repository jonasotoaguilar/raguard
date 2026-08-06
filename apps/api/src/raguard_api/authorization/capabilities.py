"""Capability tokens and the default role matrix (task 3.5).

The token constants are the single source of capability names; the allowlist
is verified against the roles.capabilities CHECK constraint from the identity
migration so the matrix and the database can never drift apart. Admin grants
every declared capability; member grants corpus view and chat only; custom
roles receive grants from their stored role row, never from a default here.
"""

from raguard_api.identity.models import ALLOWED_CAPABILITIES as _ALLOWED

ORG_SETTINGS_MANAGE = "org.settings.manage"
USERS_MANAGE = "users.manage"
DOCUMENTS_MANAGE = "documents.manage"
CORPUS_VIEW = "corpus.view"
CHAT_USE = "chat.use"

# All capability names the system knows; must equal the migration allowlist.
ALL_CAPABILITIES = frozenset(_ALLOWED)

ADMIN_CAPABILITIES = ALL_CAPABILITIES
MEMBER_CAPABILITIES = frozenset({CORPUS_VIEW, CHAT_USE})

DEFAULT_ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "admin": ADMIN_CAPABILITIES,
    "member": MEMBER_CAPABILITIES,
}


def capabilities_for_role(role_name: str) -> frozenset[str] | None:
    """Return the default grants for a built-in role, or None for unknown roles."""
    return DEFAULT_ROLE_CAPABILITIES.get(role_name)
