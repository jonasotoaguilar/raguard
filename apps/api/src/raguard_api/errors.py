"""Standardized error envelope ``{error: {code, message, details?}}`` (task 2.4).

Status mapping: 400 validation, 401 authentication, 403 authorization,
404 missing/hidden resource, 409 conflict, 503 dependency, 500 generic with a
request id. Auth failures never disclose which credential failed. Validation
details keep only stable ``loc``/``type``/``msg`` — raw input, error context,
and pydantic URLs are never serialized (jwt-authentication secrecy).
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class APIError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details=None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationError(APIError):
    status_code = 400
    code = "invalid_request"


class AuthenticationError(APIError):
    status_code = 401
    code = "authentication_failed"


class AuthorizationError(APIError):
    status_code = 403
    code = "forbidden"


class NotFoundError(APIError):
    status_code = 404
    code = "not_found"


class ConflictError(APIError):
    status_code = 409
    code = "conflict"


class ServiceUnavailableError(APIError):
    status_code = 503
    code = "service_unavailable"


def _envelope(code: str, message: str, *, details=None) -> dict:
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


_VALIDATION_DETAIL_ALLOWLIST = ("loc", "type", "msg")


def _sanitize_validation_details(details: list[dict]) -> list[dict]:
    """Allowlist-only validation details: stable loc/type/msg, never raw input.

    Pydantic error entries may carry ``input`` (the client-supplied value),
    ``ctx`` (error context) and ``url``; any of them could echo secrets back to
    the caller, so only the stable diagnostic fields are kept.
    """
    return [
        {key: entry[key] for key in _VALIDATION_DETAIL_ALLOWLIST if key in entry}
        for entry in details
    ]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error(request: Request, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, details=exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content=_envelope(
                "invalid_request",
                "Invalid request payload",
                details=_sanitize_validation_details(exc.errors()),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        request_id = uuid.uuid4().hex
        logger.exception("unhandled error request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content=_envelope(
                "internal_error", "Internal error", details={"request_id": request_id}
            ),
        )
