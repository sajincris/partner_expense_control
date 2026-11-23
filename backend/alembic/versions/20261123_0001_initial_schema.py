"""Initial schema: identity, master data, budgets, expense reports, workflow, audit.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-23
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

ENUMS = {
    "role_code": ("PARTNER", "PROJECT_MANAGER", "FINANCE_OFFICER", "FINANCE_LEAD", "AUDITOR"),
    "report_status": ("DRAFT", "SUBMITTED", "AUTO_ACCEPTED", "PENDING_PM_REVIEW", "PENDING_FINANCE_REVIEW",
                      "RETURNED_FOR_CLARIFICATION", "APPROVED", "REJECTED", "CANCELLED"),
    "workflow_action": ("SUBMIT", "AUTO_ACCEPT", "ROUTE_TO_PM", "APPROVE", "REJECT", "RETURN", "RESUBMIT", "CANCEL"),
    "review_stage": ("PARTNER", "SYSTEM", "PM", "FINANCE"),
    "exception_type": ("VARIANCE_OVER_TOLERANCE", "NO_PLAN_LINE", "DUPLICATE_INVOICE", "MISSING_DOCUMENT", "OVER_ANNUAL_BUDGET"),
    "exception_severity": ("LOW", "MEDIUM", "HIGH"),
    "exception_status": ("OPEN", "RESOLVED", "REJECTED", "SUPERSEDED"),
    "variance_direction": ("BOTH", "OVERSPEND_ONLY"),
    "budget_version_status": ("DRAFT", "ACTIVE", "SUPERSEDED"),
    "period_status": ("OPEN", "CLOSED"),
}


def E(name: str):
    return pg.ENUM(*ENUMS[name], name=name, create_type=False)


MONEY = sa.Numeric(18, 2)
TS = sa.DateTime(timezone=True)


def ts_cols():
    return [
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    ]


def soft_delete_cols():
    return [
        sa.Column("is_deleted", sa.Boolean, server_default=sa.false(), nullable=False),
        sa.Column("deleted_at", TS),
        sa.Column("deleted_by_id", sa.Integer),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        pg.ENUM(*values, name=name).create(bind, checkfirst=True)

    # ---------------------------------------------------------------- reference data
    op.create_table("currencies",
        sa.Column("code", sa.String(3), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("minor_units", sa.Integer, nullable=False, server_default="2"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *ts_cols())
    op.create_table("roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", E("role_code"), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500)),
        *ts_cols())
    op.create_table("partners",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("registration_number", sa.String(50)),
        sa.Column("country", sa.String(2)),
        sa.Column("contact_email", sa.String(255)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *ts_cols(), *soft_delete_cols())
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("partner_id", sa.Integer, sa.ForeignKey("partners.id", ondelete="RESTRICT")),
        sa.Column("last_login_at", TS),
        *ts_cols(), *soft_delete_cols())
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_partner_id", "users", ["partner_id"])
    op.create_table("user_roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("granted_by_id", sa.Integer, sa.ForeignKey("users.id")),
        *ts_cols(),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"))
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_table("exchange_rates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("from_currency", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("to_currency", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("rate_date", sa.Date, nullable=False),
        sa.Column("source", sa.String(100)),
        *ts_cols(),
        sa.UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_fx_pair_date"),
        sa.CheckConstraint("rate > 0", name="ck_fx_rate_positive"),
        sa.CheckConstraint("from_currency <> to_currency", name="ck_fx_distinct_pair"))
    op.create_index("ix_exchange_rates_rate_date", "exchange_rates", ["rate_date"])
    op.create_table("projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("donor", sa.String(200)),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("currency", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("project_manager_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *ts_cols(), *soft_delete_cols(),
        sa.CheckConstraint("end_date >= start_date", name="ck_project_dates"))
    op.create_index("ix_projects_project_manager_id", "projects", ["project_manager_id"])
    op.create_table("project_partners",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("partner_id", sa.Integer, sa.ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("agreement_reference", sa.String(100)),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *ts_cols(),
        sa.UniqueConstraint("project_id", "partner_id", name="uq_project_partner"))
    op.create_index("ix_project_partners_project_id", "project_partners", ["project_id"])
    op.create_index("ix_project_partners_partner_id", "project_partners", ["partner_id"])
    op.create_table("cost_categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *ts_cols())
    op.create_table("gl_accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_number", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("cost_category_id", sa.Integer, sa.ForeignKey("cost_categories.id")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *ts_cols())
    op.create_table("reporting_periods",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("period", sa.Integer, nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("submission_deadline", sa.Date, nullable=False),
        sa.Column("status", E("period_status"), nullable=False, server_default="OPEN"),
        *ts_cols(),
        sa.UniqueConstraint("fiscal_year", "period", name="uq_reporting_period"),
        sa.CheckConstraint("period BETWEEN 1 AND 12", name="ck_reporting_period_month"))

    # ---------------------------------------------------------------- budgets
    op.create_table("budget_plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("partner_id", sa.Integer, sa.ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id")),
        *ts_cols(),
        sa.UniqueConstraint("partner_id", "project_id", "fiscal_year", name="uq_budget_plan_scope"))
    op.create_index("ix_budget_plans_partner_id", "budget_plans", ["partner_id"])
    op.create_index("ix_budget_plans_project_id", "budget_plans", ["project_id"])
    op.create_table("budget_plan_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("budget_plan_id", sa.Integer, sa.ForeignKey("budget_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("status", E("budget_version_status"), nullable=False, server_default="DRAFT"),
        sa.Column("change_reason", sa.Text, nullable=False),
        sa.Column("total_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("approved_by_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("approved_at", TS),
        *ts_cols(),
        sa.UniqueConstraint("budget_plan_id", "version_no", name="uq_budget_version_no"))
    op.create_index("ix_budget_plan_versions_budget_plan_id", "budget_plan_versions", ["budget_plan_id"])
    op.create_index("uq_budget_one_active_version", "budget_plan_versions", ["budget_plan_id"], unique=True,
                    postgresql_where=sa.text("status = 'ACTIVE'"))
    op.create_table("budget_plan_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("version_id", sa.Integer, sa.ForeignKey("budget_plan_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.Integer, nullable=False),
        sa.Column("cost_category_id", sa.Integer, sa.ForeignKey("cost_categories.id"), nullable=False),
        sa.Column("gl_account_id", sa.Integer, sa.ForeignKey("gl_accounts.id"), nullable=False),
        sa.Column("planned_amount", MONEY, nullable=False),
        sa.Column("notes", sa.String(500)),
        *ts_cols(),
        sa.UniqueConstraint("version_id", "period", "cost_category_id", "gl_account_id", name="uq_budget_line_key"),
        sa.CheckConstraint("period BETWEEN 1 AND 12", name="ck_budget_line_period"),
        sa.CheckConstraint("planned_amount >= 0", name="ck_budget_line_non_negative"))
    op.create_index("ix_budget_line_lookup", "budget_plan_lines", ["version_id", "cost_category_id", "gl_account_id"])

    # ---------------------------------------------------------------- configuration
    op.create_table("tolerance_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("partner_id", sa.Integer, sa.ForeignKey("partners.id")),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id")),
        sa.Column("cost_category_id", sa.Integer, sa.ForeignKey("cost_categories.id")),
        sa.Column("max_variance_pct", sa.Numeric(9, 4), nullable=False),
        sa.Column("max_variance_abs", MONEY, nullable=False),
        sa.Column("abs_currency", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("direction", E("variance_direction"), nullable=False, server_default="BOTH"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *ts_cols(),
        sa.CheckConstraint("max_variance_pct >= 0", name="ck_rule_pct_non_negative"),
        sa.CheckConstraint("max_variance_abs >= 0", name="ck_rule_abs_non_negative"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_rule_dates"))
    op.create_index("ix_rule_scope", "tolerance_rules", ["project_id", "partner_id", "cost_category_id"])
    op.create_table("system_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", pg.JSONB, nullable=False),
        sa.Column("description", sa.String(500)),
        *ts_cols())

    # ---------------------------------------------------------------- expense reports
    op.create_table("expense_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_number", sa.String(40), nullable=False, unique=True),
        sa.Column("partner_id", sa.Integer, sa.ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("budget_plan_version_id", sa.Integer, sa.ForeignKey("budget_plan_versions.id")),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("period", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("status", E("report_status"), nullable=False, server_default="DRAFT"),
        sa.Column("total_amount", MONEY, nullable=False, server_default="0"),
        sa.Column("partner_comment", sa.Text),
        sa.Column("requires_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("submission_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("submitted_at", TS),
        sa.Column("pm_approved_by_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("pm_approved_at", TS),
        sa.Column("finance_approved_by_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("finance_approved_at", TS),
        sa.Column("review_due_at", TS),
        sa.Column("closed_at", TS),
        *ts_cols(),
        sa.CheckConstraint("period BETWEEN 1 AND 12", name="ck_report_period"),
        sa.CheckConstraint("total_amount >= 0", name="ck_report_total_non_negative"),
        # Control: an APPROVED report must carry both approvals, by different people.
        sa.CheckConstraint(
            "status <> 'APPROVED' OR (pm_approved_by_id IS NOT NULL AND finance_approved_by_id IS NOT NULL "
            "AND pm_approved_by_id <> finance_approved_by_id)",
            name="ck_report_approved_needs_two_approvers"))
    op.create_index("ix_expense_reports_partner_id", "expense_reports", ["partner_id"])
    op.create_index("ix_expense_reports_project_id", "expense_reports", ["project_id"])
    op.create_index("ix_report_status", "expense_reports", ["status"])
    op.create_index("ix_report_project_period", "expense_reports", ["project_id", "fiscal_year", "period"])
    op.create_index("ix_expense_reports_review_due_at", "expense_reports", ["review_due_at"])
    op.create_index("uq_report_live_per_period", "expense_reports", ["partner_id", "project_id", "fiscal_year", "period"],
                    unique=True, postgresql_where=sa.text("status NOT IN ('CANCELLED', 'REJECTED')"))
    op.create_table("expense_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_id", sa.Integer, sa.ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("expense_date", sa.Date, nullable=False),
        sa.Column("cost_category_id", sa.Integer, sa.ForeignKey("cost_categories.id"), nullable=False),
        sa.Column("gl_account_id", sa.Integer, sa.ForeignKey("gl_accounts.id"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(3), sa.ForeignKey("currencies.code"), nullable=False),
        sa.Column("invoice_reference", sa.String(100), nullable=False),
        sa.Column("matched_plan_line_id", sa.Integer, sa.ForeignKey("budget_plan_lines.id")),
        *ts_cols(), *soft_delete_cols(),
        sa.CheckConstraint("amount > 0", name="ck_expense_line_positive"))
    op.create_index("ix_expense_line_report", "expense_lines", ["report_id"])
    op.create_index("ix_expense_line_invoice", "expense_lines", ["invoice_reference"])
    op.create_table("expense_attachments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_id", sa.Integer, sa.ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expense_line_id", sa.Integer, sa.ForeignKey("expense_lines.id", ondelete="CASCADE")),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        *ts_cols(), *soft_delete_cols(),
        sa.CheckConstraint("size_bytes > 0", name="ck_attachment_size"))
    op.create_index("ix_expense_attachments_report_id", "expense_attachments", ["report_id"])
    op.create_index("ix_expense_attachments_expense_line_id", "expense_attachments", ["expense_line_id"])

    # ---------------------------------------------------------------- workflow
    op.create_table("variance_reviews",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_id", sa.Integer, sa.ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submission_no", sa.Integer, nullable=False, server_default="1"),
        sa.Column("expense_line_id", sa.Integer, sa.ForeignKey("expense_lines.id")),
        sa.Column("exception_type", E("exception_type"), nullable=False),
        sa.Column("severity", E("exception_severity"), nullable=False),
        sa.Column("status", E("exception_status"), nullable=False, server_default="OPEN"),
        sa.Column("cost_category_id", sa.Integer, sa.ForeignKey("cost_categories.id")),
        sa.Column("gl_account_id", sa.Integer, sa.ForeignKey("gl_accounts.id")),
        sa.Column("planned_amount", MONEY),
        sa.Column("actual_amount", MONEY),
        sa.Column("variance_amount", MONEY),
        sa.Column("variance_pct", sa.Numeric(9, 4)),
        sa.Column("tolerance_rule_id", sa.Integer, sa.ForeignKey("tolerance_rules.id")),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("calculation_snapshot", pg.JSONB),
        sa.Column("pm_justification", sa.Text),
        sa.Column("finance_note", sa.Text),
        sa.Column("resolved_at", TS),
        *ts_cols())
    op.create_index("ix_variance_review_report", "variance_reviews", ["report_id"])
    op.create_index("ix_variance_review_status_type", "variance_reviews", ["status", "exception_type"])
    op.create_table("approval_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_id", sa.Integer, sa.ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", E("review_stage"), nullable=False),
        sa.Column("action", E("workflow_action"), nullable=False),
        sa.Column("from_status", E("report_status"), nullable=False),
        sa.Column("to_status", E("report_status"), nullable=False),
        sa.Column("comment", sa.Text),
        sa.Column("checklist", pg.JSONB),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", TS, nullable=False))
    op.create_index("ix_approval_action_report", "approval_actions", ["report_id", "created_at"])

    # ---------------------------------------------------------------- audit & notifications
    op.create_table("audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.String(60), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("old_values", pg.JSONB),
        sa.Column("new_values", pg.JSONB),
        sa.Column("comment", sa.Text),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("actor_email", sa.String(255)),
        sa.Column("actor_roles", sa.String(200)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False))
    op.create_index("ix_audit_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_created", "audit_logs", ["created_at"])
    op.create_index("ix_audit_actor", "audit_logs", ["actor_id"])
    op.create_table("notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("entity_type", sa.String(60)),
        sa.Column("entity_id", sa.Integer),
        sa.Column("read_at", TS),
        *ts_cols())
    op.create_index("ix_notification_user_unread", "notifications", ["user_id", "read_at"])

    # ---------------------------------------------------------------- database-level controls
    # 1. The audit trail and the approval journal are append-only, even for a DBA using the app role.
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("audit_logs", "approval_actions"):
        op.execute(f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION forbid_mutation();")
    # 2. Lines of a report that is no longer editable cannot be changed by any code path.
    op.execute("""
        CREATE OR REPLACE FUNCTION lock_closed_report_lines() RETURNS trigger AS $$
        DECLARE s report_status;
        BEGIN
            SELECT status INTO s FROM expense_reports WHERE id = COALESCE(NEW.report_id, OLD.report_id);
            IF s NOT IN ('DRAFT', 'RETURNED_FOR_CLARIFICATION') THEN
                RAISE EXCEPTION 'expense lines of a % report are locked', s;
            END IF;
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("CREATE TRIGGER trg_expense_lines_lock BEFORE INSERT OR UPDATE OR DELETE ON expense_lines "
               "FOR EACH ROW EXECUTE FUNCTION lock_closed_report_lines();")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_expense_lines_lock ON expense_lines")
    for table in ("audit_logs", "approval_actions"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS lock_closed_report_lines()")
    op.execute("DROP FUNCTION IF EXISTS forbid_mutation()")
    for table in ("notifications", "audit_logs", "approval_actions", "variance_reviews", "expense_attachments",
                  "expense_lines", "expense_reports", "system_settings", "tolerance_rules", "budget_plan_lines",
                  "budget_plan_versions", "budget_plans", "reporting_periods", "gl_accounts", "cost_categories",
                  "project_partners", "projects", "exchange_rates", "user_roles", "users", "partners", "roles", "currencies"):
        op.drop_table(table)
    bind = op.get_bind()
    for name in ENUMS:
        pg.ENUM(name=name).drop(bind, checkfirst=True)
