"""Domain exceptions and global exception handlers.

Features raise these typed exceptions instead of constructing ``HTTPException``
directly. A single set of handlers (registered in ``main.py``) converts them to
a uniform JSON error envelope so the frontend always sees the same shape:

    {"error": {"code": "not_found", "message": "...", "details": {...}}}
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppException(Exception):
    """Base class for all expected, handled application errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "app_error"
    message: str = "Application error"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Resource not found"


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "Resource conflict"


class ValidationError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"
    message = "Invalid input"


class AuthenticationError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "authentication_error"
    message = "Authentication failed"


class PermissionDeniedError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "You do not have permission to perform this action"


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_exception_handlers(app) -> None:
    @app.exception_handler(AppException)
    async def _handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        if exc.status_code >= 500:
            logger.exception("Unhandled app exception: %s", exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        raw = exc.errors()
        # Drop pydantic's ``ctx`` — for custom validators it holds the raw
        # ValueError, which isn't JSON-serializable. jsonable_encoder makes the
        # rest (tuples, Decimals, …) safe.
        errors = [{k: v for k, v in err.items() if k != "ctx"} for err in raw]
        # Surface the first concrete message so the UI can show something useful.
        first = (raw[0].get("msg") if raw else "") or "Request validation failed"
        message = first.removeprefix("Value error, ")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                "validation_error",
                message,
                {"errors": jsonable_encoder(errors)},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("http_error", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unexpected error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "An unexpected error occurred"),
        )
