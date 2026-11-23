"""Import every model so SQLAlchemy metadata (and Alembic) sees the full schema."""
from app.models.base import Base
from app.models.budget import BudgetPlan, BudgetPlanLine, BudgetPlanVersion
from app.models.expense import ExpenseAttachment, ExpenseLine, ExpenseReport
from app.models.identity import Role, User, UserRole
from app.models.master_data import (
    CostCategory,
    Currency,
    ExchangeRate,
    GLAccount,
    Partner,
    Project,
    ProjectPartner,
    ReportingPeriod,
)
from app.models.review import ApprovalAction, VarianceReview
from app.models.system import AuditLog, Notification, SystemSetting, ToleranceRule

__all__ = [
    "Base",
    "Role",
    "User",
    "UserRole",
    "Partner",
    "Project",
    "ProjectPartner",
    "Currency",
    "ExchangeRate",
    "CostCategory",
    "GLAccount",
    "ReportingPeriod",
    "BudgetPlan",
    "BudgetPlanVersion",
    "BudgetPlanLine",
    "ExpenseReport",
    "ExpenseLine",
    "ExpenseAttachment",
    "VarianceReview",
    "ApprovalAction",
    "ToleranceRule",
    "SystemSetting",
    "AuditLog",
    "Notification",
]
