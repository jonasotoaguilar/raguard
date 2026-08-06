"""Protected /api/org administration routes (task 3.7).

Every route obtains authorization through the single fresh resolver, which
derives tenant identity exclusively from the verified cookie JWT; no route
accepts tenant identity from path, body, query, or headers. Targets outside
the caller's tenant are indistinguishable from missing targets (neutral 404),
members cannot escalate to admin operations (403), and capability updates
apply on the caller's next request (no permission cache).
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.authorization.capabilities import ALL_CAPABILITIES
from raguard_api.authorization.resolver import (
    AuthorizationResolver,
    create_scope_dependency,
)
from raguard_api.authorization.scope import AuthorizationScope
from raguard_api.errors import AuthorizationError, NotFoundError, ValidationError
from raguard_api.identity.models import Membership, Role, User


class UpdateRoleRequest(BaseModel):
    capabilities: list[str] = Field(min_length=1)


class UpdateMembershipRequest(BaseModel):
    role_id: uuid.UUID


def create_org_router(*, session_factory: async_sessionmaker[AsyncSession]) -> APIRouter:
    resolver = AuthorizationResolver(session_factory=session_factory)
    GetScope = Annotated[AuthorizationScope, Depends(create_scope_dependency(resolver))]

    def require_capability(capability: str):
        """Dependency: allow only scopes holding the capability (403 otherwise)."""

        def _require(scope: GetScope) -> AuthorizationScope:
            if not scope.has_capability(capability):
                raise AuthorizationError("Insufficient permissions")
            return scope

        return _require

    router = APIRouter(prefix="/api/org", tags=["org"])

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    @router.get("/users")
    async def list_users(
        scope: Annotated[AuthorizationScope, Depends(require_capability("users.manage"))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        rows = (
            await session.execute(
                select(User.id, User.email)
                .join(Membership, Membership.user_id == User.id)
                .where(Membership.tenant_id == scope.tenant_id)
                .order_by(User.email)
            )
        ).all()
        return {"users": [{"id": str(user_id), "email": email} for user_id, email in rows]}

    @router.get("/users/{user_id}")
    async def get_user(
        user_id: uuid.UUID,
        scope: Annotated[AuthorizationScope, Depends(require_capability("users.manage"))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        row = (
            await session.execute(
                select(User.id, User.email)
                .join(Membership, Membership.user_id == User.id)
                .where(Membership.tenant_id == scope.tenant_id, User.id == user_id)
            )
        ).first()
        if row is None:
            raise NotFoundError("User not found")
        return {"id": str(row.id), "email": row.email}

    @router.get("/roles")
    async def list_roles(
        scope: Annotated[AuthorizationScope, Depends(require_capability("org.settings.manage"))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        rows = (
            await session.execute(
                select(Role.id, Role.name, Role.capabilities)
                .where(Role.tenant_id == scope.tenant_id)
                .order_by(Role.name)
            )
        ).all()
        return {
            "roles": [
                {"id": str(role_id), "name": name, "capabilities": list(capabilities)}
                for role_id, name, capabilities in rows
            ]
        }

    @router.patch("/roles/{role_id}")
    async def update_role(
        role_id: uuid.UUID,
        payload: UpdateRoleRequest,
        scope: Annotated[AuthorizationScope, Depends(require_capability("org.settings.manage"))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        role = (
            await session.execute(
                select(Role).where(Role.id == role_id, Role.tenant_id == scope.tenant_id)
            )
        ).scalar_one_or_none()
        if role is None:
            raise NotFoundError("Role not found")
        unknown = sorted(set(payload.capabilities) - set(ALL_CAPABILITIES))
        if unknown:
            raise ValidationError(f"Unknown capabilities: {', '.join(unknown)}")
        role.capabilities = payload.capabilities
        await session.commit()
        return {"id": str(role.id), "name": role.name, "capabilities": list(role.capabilities)}

    @router.get("/memberships")
    async def list_memberships(
        scope: Annotated[AuthorizationScope, Depends(require_capability("users.manage"))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        rows = (
            await session.execute(
                select(Membership.id, User.email, Role.name)
                .join(User, User.id == Membership.user_id)
                .join(
                    Role,
                    and_(Role.id == Membership.role_id, Role.tenant_id == Membership.tenant_id),
                )
                .where(Membership.tenant_id == scope.tenant_id)
                .order_by(User.email)
            )
        ).all()
        return {
            "memberships": [
                {"id": str(membership_id), "user_email": email, "role": role_name}
                for membership_id, email, role_name in rows
            ]
        }

    @router.patch("/memberships/{membership_id}")
    async def update_membership(
        membership_id: uuid.UUID,
        payload: UpdateMembershipRequest,
        scope: Annotated[AuthorizationScope, Depends(require_capability("users.manage"))],
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        membership = (
            await session.execute(
                select(Membership).where(
                    Membership.id == membership_id, Membership.tenant_id == scope.tenant_id
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise NotFoundError("Membership not found")
        role = (
            await session.execute(
                select(Role.id).where(Role.id == payload.role_id, Role.tenant_id == scope.tenant_id)
            )
        ).scalar_one_or_none()
        if role is None:
            raise NotFoundError("Role not found")
        membership.role_id = payload.role_id
        await session.commit()
        return {"id": str(membership.id), "role_id": str(membership.role_id)}

    return router
