import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import DomainError

logger = logging.getLogger("pec")

TAGS = [
    {"name": "Authentication", "description": "JWT login. Use **Authorize** with a demo user (see README)."},
    {"name": "Expense reports", "description": "Partner reporting: drafts, lines, documents, submission."},
    {"name": "Variance reviews", "description": "Exception queue, PM review, Finance validation."},
    {"name": "Budget plans", "description": "Approved plans with versioning and maker-checker activation."},
    {"name": "Dashboard & reports", "description": "Plan vs actual, variances, exports (CSV/XLSX)."},
    {"name": "Audit trail", "description": "Append-only log of every change with old/new values."},
    {"name": "Configuration", "description": "Tolerance rules, settings, reporting periods (Finance Lead)."},
]

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "Plan vs Actual monitoring and variance approval for partner expense reports. "
        "All error responses share the envelope `{\"error\": {\"code\", \"message\", \"details\"}}`."
    ),
    openapi_tags=TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Request-ID"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details or {}}})


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    return _error(exc.status_code, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
    return _error(422, "REQUEST_VALIDATION_FAILED", "The request is invalid.", {"errors": details})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, exc: IntegrityError):
    logger.warning("Integrity error: %s", exc.orig)
    return _error(409, "INTEGRITY_CONSTRAINT", "The operation violates a data integrity rule.")


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
