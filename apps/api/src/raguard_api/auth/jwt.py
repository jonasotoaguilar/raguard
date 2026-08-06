"""Thin HS256 JWT: issuance and strict verification (task 2.6).

The token carries only DB-derived identity claims (sub, tid) plus the standard
iat/exp/iss/aud/jti. Roles and capabilities are intentionally absent so
permission changes apply immediately on the next request; the tenant is
resolved exclusively from the verified ``tid`` claim. Verification always uses
the configured secret, a fixed HS256 algorithm, and the configured
issuer/audience — never values taken from the token itself.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt as pyjwt

from raguard_api.config import Settings

REQUIRED_CLAIMS = ("sub", "tid", "iss", "aud", "iat", "exp", "jti")


class InvalidToken(Exception):
    """Expired, forged, tampered, malformed, or otherwise unverifiable token."""


@dataclass(frozen=True)
class TokenClaims:
    sub: uuid.UUID
    tid: uuid.UUID
    iat: datetime
    exp: datetime
    jti: str


def create_access_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
        "jti": uuid.uuid4().hex,
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> TokenClaims:
    try:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": list(REQUIRED_CLAIMS)},
        )
        return TokenClaims(
            sub=uuid.UUID(payload["sub"]),
            tid=uuid.UUID(payload["tid"]),
            iat=datetime.fromtimestamp(payload["iat"], tz=UTC),
            exp=datetime.fromtimestamp(payload["exp"], tz=UTC),
            jti=payload["jti"],
        )
    except (pyjwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise InvalidToken(str(exc)) from exc
