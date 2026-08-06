"""AuthorizationScope: identity plus role grants, rendered as SQL predicates (task 3.5).

Scopes are derived server-side from verified identity and current role state
and emit parameterized SQLAlchemy expressions — never SQL strings, never
client-supplied literals — so future retrieval and citation queries can
compose the tenant predicate before generation (ADR-0002/0003). A capability
that is not granted yields False.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.sql.elements import ColumnElement


@dataclass(frozen=True, slots=True)
class AuthorizationScope:
    """The granted scope for one user inside one tenant for one request."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    capabilities: frozenset[str]

    def has_capability(self, capability: str) -> bool:
        """True only when the role grant set contains the capability."""
        return capability in self.capabilities

    def tenant_predicate(self, tenant_column: ColumnElement) -> ColumnElement[bool]:
        """A parameterized equality predicate binding this scope's tenant id.

        The returned expression compares the given column against a bound
        parameter; the tenant id never appears as a literal in the SQL text.
        """
        return tenant_column == self.tenant_id
