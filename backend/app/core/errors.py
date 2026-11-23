"""Domain errors mapped to a single, predictable API error envelope.

Every error response has the shape:
    {"error": {"code": "...", "message": "...", "details": {...}}}
"""
from typing import Any


class DomainError(Exception):
    status_code = 400
    code = "DOMAIN_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code:
            self.code = code


class NotFoundError(DomainError):
    status_code = 404
    code = "NOT_FOUND"


class PermissionDeniedError(DomainError):
    status_code = 403
    code = "FORBIDDEN"


class SegregationOfDutiesError(DomainError):
    status_code = 403
    code = "SEGREGATION_OF_DUTIES"


class InvalidTransitionError(DomainError):
    status_code = 409
    code = "INVALID_STATUS_TRANSITION"


class ValidationFailedError(DomainError):
    status_code = 422
    code = "BUSINESS_VALIDATION_FAILED"


class ConflictError(DomainError):
    status_code = 409
    code = "CONFLICT"


class AuthenticationError(DomainError):
    status_code = 401
    code = "UNAUTHENTICATED"
