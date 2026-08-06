"""POST /api/auth/login (task 2.8).

Canonical email lookup, password verification with vetted Argon2id, an
unambiguous membership (exactly one tenant) selected server-side, and a thin
JWT delivered only as an HttpOnly cookie. Wrong email and wrong password are
indistinguishable; foreign Origins are rejected; no credentials or hashes are
ever logged or returned.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from raguard_api.auth.jwt import create_access_token
from raguard_api.auth.passwords import hash_password, needs_rehash, verify_password
from raguard_api.config import Settings
from raguard_api.errors import AuthenticationError, AuthorizationError
from raguard_api.identity.models import Membership, User

GENERIC_AUTH_MESSAGE = "Invalid email or password"


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


def create_auth_router(
    *, settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    @router.post("/login")
    async def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
        session: Annotated[AsyncSession, Depends(_session)],
    ) -> dict:
        _reject_foreign_origin(request, settings)
        email = payload.email.strip().lower()
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None or not verify_password(payload.password, user.password_hash):
            raise AuthenticationError(GENERIC_AUTH_MESSAGE)
        tenant_id = await _unambiguous_tenant(session, user.id)
        if tenant_id is None:
            raise AuthenticationError(GENERIC_AUTH_MESSAGE)
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(payload.password)
            await session.commit()
        token = create_access_token(user_id=user.id, tenant_id=tenant_id, settings=settings)
        response.set_cookie(
            settings.session_cookie_name,
            token,
            max_age=settings.jwt_expiry_minutes * 60,
            path=settings.session_cookie_path,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite=settings.session_cookie_samesite,
        )
        return {"message": "ok"}

    return router


async def _unambiguous_tenant(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    tenant_ids = (
        (await session.execute(select(Membership.tenant_id).where(Membership.user_id == user_id)))
        .scalars()
        .all()
    )
    return tenant_ids[0] if len(tenant_ids) == 1 else None


def _reject_foreign_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins:
        raise AuthorizationError("Origin not allowed")
