"""Domain enumerations.

Kept framework-free so the workflow and variance engines can be unit-tested
without a database or web framework.
"""
from enum import StrEnum


class RoleCode(StrEnum):
    PARTNER = "PARTNER"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    FINANCE_OFFICER = "FINANCE_OFFICER"
    FINANCE_LEAD = "FINANCE_LEAD"  # Finance Lead / Administrator
    AUDITOR = "AUDITOR"


class ReportStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    AUTO_ACCEPTED = "AUTO_ACCEPTED"
    PENDING_PM_REVIEW = "PENDING_PM_REVIEW"
    PENDING_FINANCE_REVIEW = "PENDING_FINANCE_REVIEW"
    RETURNED_FOR_CLARIFICATION = "RETURNED_FOR_CLARIFICATION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


EDITABLE_STATUSES = (ReportStatus.DRAFT, ReportStatus.RETURNED_FOR_CLARIFICATION)
TERMINAL_STATUSES = (
    ReportStatus.AUTO_ACCEPTED,
    ReportStatus.APPROVED,
    ReportStatus.REJECTED,
    ReportStatus.CANCELLED,
)
# Statuses whose actuals count as "booked" spend for YTD and duplicate checks.
BOOKED_STATUSES = (ReportStatus.AUTO_ACCEPTED, ReportStatus.APPROVED)
# Statuses that still "hold" an invoice reference (duplicate detection scope).
INVOICE_HOLDING_STATUSES = (
    ReportStatus.SUBMITTED,
    ReportStatus.AUTO_ACCEPTED,
    ReportStatus.PENDING_PM_REVIEW,
    ReportStatus.PENDING_FINANCE_REVIEW,
    ReportStatus.RETURNED_FOR_CLARIFICATION,
    ReportStatus.APPROVED,
)


class WorkflowAction(StrEnum):
    SUBMIT = "SUBMIT"
    AUTO_ACCEPT = "AUTO_ACCEPT"
    ROUTE_TO_PM = "ROUTE_TO_PM"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    RETURN = "RETURN"
    RESUBMIT = "RESUBMIT"
    CANCEL = "CANCEL"


class ReviewStage(StrEnum):
    PARTNER = "PARTNER"
    SYSTEM = "SYSTEM"
    PM = "PM"
    FINANCE = "FINANCE"


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    RETURN = "RETURN"


class ExceptionType(StrEnum):
    VARIANCE_OVER_TOLERANCE = "VARIANCE_OVER_TOLERANCE"
    NO_PLAN_LINE = "NO_PLAN_LINE"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    OVER_ANNUAL_BUDGET = "OVER_ANNUAL_BUDGET"


class ExceptionSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ExceptionStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"  # report approved with the exception justified
    REJECTED = "REJECTED"  # report rejected
    SUPERSEDED = "SUPERSEDED"  # report resubmitted, exception re-evaluated


class VarianceDirection(StrEnum):
    BOTH = "BOTH"  # |variance| is tested (literal policy reading)
    OVERSPEND_ONLY = "OVERSPEND_ONLY"  # only actual > plan is tested


class MissingDocumentPolicy(StrEnum):
    BLOCK = "BLOCK"  # submission refused
    REQUIRE_REVIEW = "REQUIRE_REVIEW"  # exception created, manual review


class BudgetVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class PeriodStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SOFT_DELETE = "SOFT_DELETE"
    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    STATUS_CHANGE = "STATUS_CHANGE"
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    RETURN = "RETURN"
    COMMENT = "COMMENT"
    UPLOAD = "UPLOAD"
    EXPORT = "EXPORT"
    CONFIG_CHANGE = "CONFIG_CHANGE"
