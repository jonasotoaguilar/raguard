"""Authentication dependency: verified token, tenant only from ``tid`` (task 2.7).

Protected routes depend on this to resolve identity. The token must arrive via
the session cookie; no tenant or identity value is ever accepted from body,
query, path, or headers.
"""

from typing import Annotated

from fastapi import Depends, Request

from raguard_api.auth.jwt import InvalidToken, TokenClaims, decode_access_token
from raguard_api.config import Settings, get_settings
from raguard_api.errors import AuthenticationError


def get_token_claims(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> TokenClaims:
    token = request.cookies.get(settings.session_cookie_name)
    if token is None:
        raise AuthenticationError("Authentication required")
    try:
        return decode_access_token(token, settings)
    except InvalidToken as exc:
        raise AuthenticationError("Invalid or expired session") from exc
