"""Unit tests: HS256 JWT issuance and verification (task 2.2).

Drives ``raguard_api.auth.jwt``: the issued token carries exactly the required
claims (sub, tid, iss, aud, iat, exp, jti) with a fixed HS256 algorithm and no
permission claims; expired, forged, tampered, malformed, wrong-issuer/audience,
and claim-missing tokens are all rejected.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from jwt.utils import base64url_decode, base64url_encode
from raguard_api.auth.jwt import InvalidToken, create_access_token, decode_access_token
from raguard_api.config import Settings

pytestmark = pytest.mark.unit

USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
TENANT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def settings():
    return Settings(
        jwt_secret="unit-test-secret-0123456789abcdef",
        jwt_issuer="raguard-tests",
        jwt_audience="raguard-api",
    )


def _signed(settings, **overrides) -> str:
    payload = {
        "sub": str(USER_ID),
        "tid": str(TENANT_ID),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=15),
        "jti": uuid.uuid4().hex,
        **overrides,
    }
    secret = payload.pop("_secret", settings.jwt_secret)
    return pyjwt.encode(payload, secret, algorithm="HS256")


def _tamper(token: str, claim: str, value: str) -> str:
    """Modify a claim while keeping the original signature (signature mismatch)."""
    header, payload, signature = token.split(".")
    data = json.loads(base64url_decode(payload.encode()))
    data[claim] = value
    altered = base64url_encode(json.dumps(data).encode()).decode()
    return f"{header}.{altered}.{signature}"


def test_issued_token_has_required_claims_fixed_alg_and_no_permissions(settings):
    token = create_access_token(user_id=USER_ID, tenant_id=TENANT_ID, settings=settings)
    assert pyjwt.get_unverified_header(token)["alg"] == "HS256"
    payload = pyjwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"], audience=settings.jwt_audience
    )
    assert {"sub", "tid", "iss", "aud", "iat", "exp", "jti"} <= set(payload)
    assert not {"roles", "capabilities", "tenant"} & set(payload)


def test_issued_token_verifies_with_configured_secret(settings):
    claims = decode_access_token(
        create_access_token(user_id=USER_ID, tenant_id=TENANT_ID, settings=settings), settings
    )
    assert claims.sub == USER_ID
    assert claims.tid == TENANT_ID
    assert claims.exp > claims.iat
    assert claims.jti


def test_expired_token_rejected(settings):
    token = _signed(settings, exp=datetime.now(UTC) - timedelta(minutes=1))
    with pytest.raises(InvalidToken):
        decode_access_token(token, settings)


def test_forged_token_rejected(settings):
    token = _signed(settings, _secret="attacker-secret-0123456789abcdef")
    with pytest.raises(InvalidToken):
        decode_access_token(token, settings)


def test_tampered_tenant_claim_rejected(settings):
    token = _tamper(_signed(settings), "tid", str(uuid.uuid4()))
    with pytest.raises(InvalidToken):
        decode_access_token(token, settings)


def test_malformed_token_rejected(settings):
    with pytest.raises(InvalidToken):
        decode_access_token("not.a.jwt", settings)


def test_wrong_issuer_or_audience_rejected(settings):
    for issuer, audience in (
        ("other-issuer", settings.jwt_audience),
        (settings.jwt_issuer, "other-audience"),
    ):
        with pytest.raises(InvalidToken):
            decode_access_token(_signed(settings, iss=issuer, aud=audience), settings)


def test_missing_required_claim_rejected(settings):
    token = _signed(settings)
    payload = pyjwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"], audience=settings.jwt_audience
    )
    del payload["jti"]
    with pytest.raises(InvalidToken):
        decode_access_token(pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256"), settings)
