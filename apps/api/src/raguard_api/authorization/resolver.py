"""The single fresh-per-request authorization resolver (task 3.6).

Resolution maps verified JWT claims (sub, tid) onto current database
membership/role state and returns an AuthorizationScope. The resolver holds no
capability state: every call runs a fresh, parameterized query, so role
changes apply on the next request without cache invalidation. All protected
routes must obtain authorization through this one function; route-local
checks are forbidden (spec authorization-rbac).
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.auth.dependencies import get_token_claims
from raguard_api.auth.jwt import TokenClaims
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.errors import AuthenticationError
from raguard_api.identity.models import Membership, Role


class AuthorizationResolver:
    """Stateless resolver; safe to share across requests and routers."""

    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve(self, claims: TokenClaims) -> AuthorizationScope:
        """Resolve the current role grants for the verified identity."""
        statement = (
            select(Role.capabilities)
            .join(
                Membership,
                and_(Membership.role_id == Role.id, Membership.tenant_id == Role.tenant_id),
            )
            .where(Membership.user_id == claims.sub, Membership.tenant_id == claims.tid)
        )
        async with self._session_factory() as session:
            capabilities = (await session.execute(statement)).scalar_one_or_none()
        if capabilities is None:
            raise AuthenticationError("Authentication required")
        return AuthorizationScope(
            tenant_id=claims.tid,
            user_id=claims.sub,
            capabilities=frozenset(capabilities),
        )


def create_scope_dependency(resolver: AuthorizationResolver):
    """FastAPI dependency: verified claims -> fresh AuthorizationScope."""

    async def get_authorization_scope(
        claims: Annotated[TokenClaims, Depends(get_token_claims)],
    ):
        return await resolver.resolve(claims)

    return get_authorization_scope
