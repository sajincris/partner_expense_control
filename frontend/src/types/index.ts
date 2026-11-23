// Money values are transported as decimal strings to avoid floating-point drift.
export type Money = string;

export type RoleCode = "PARTNER" | "PROJECT_MANAGER" | "FINANCE_OFFICER" | "FINANCE_LEAD" | "AUDITOR";

export type ReportStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "AUTO_ACCEPTED"
  | "PENDING_PM_REVIEW"
  | "PENDING_FINANCE_REVIEW"
  | "RETURNED_FOR_CLARIFICATION"
  | "APPROVED"
  | "REJECTED"
  | "CANCELLED";

export type ExceptionType =
  | "VARIANCE_OVER_TOLERANCE"
  | "NO_PLAN_LINE"
  | "DUPLICATE_INVOICE"
  | "MISSING_DOCUMENT"
  | "OVER_ANNUAL_BUDGET";

export type Severity = "LOW" | "MEDIUM" | "HIGH";
export type Decision = "APPROVE" | "REJECT" | "RETURN";

export interface User {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  partner_id: number | null;
  partner_name: string | null;
  roles: RoleCode[];
  last_login_at: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface Partner {
  id: number;
  code: string;
  name: string;
  registration_number: string | null;
  country: string | null;
  contact_email: string | null;
  is_active: boolean;
}

export interface Project {
  id: number;
  code: string;
  name: string;
  donor: string | null;
  start_date: string;
  end_date: string;
  currency: string;
  project_manager_id: number | null;
  project_manager_name: string | null;
  is_active: boolean;
  partners: { id: number; partner_id: number; partner_name: string; agreement_reference: string | null; is_active: boolean }[];
}

export interface CostCategory { id: number; code: string; name: string }
export interface GLAccount { id: number; account_number: string; name: string; cost_category_id: number | null }

export interface Attachment {
  id: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

export interface ExpenseLine {
  id: number;
  line_no: number;
  expense_date: string;
  cost_category_id: number;
  cost_category_name: string;
  gl_account_id: number;
  gl_account_number: string;
  description: string;
  amount: Money;
  currency: string;
  invoice_reference: string;
  matched_plan_line_id: number | null;
  attachments: Attachment[];
}

export interface VarianceException {
  id: number;
  submission_no: number;
  expense_line_id: number | null;
  exception_type: ExceptionType;
  severity: Severity;
  status: "OPEN" | "RESOLVED" | "REJECTED" | "SUPERSEDED";
  cost_category_id: number | null;
  gl_account_id: number | null;
  planned_amount: Money | null;
  actual_amount: Money | null;
  variance_amount: Money | null;
  variance_pct: string | null;
  message: string;
  pm_justification: string | null;
  finance_note: string | null;
  created_at: string;
}

export interface ApprovalAction {
  id: number;
  stage: "PARTNER" | "SYSTEM" | "PM" | "FINANCE";
  action: string;
  from_status: ReportStatus;
  to_status: ReportStatus;
  comment: string | null;
  checklist: Record<string, boolean> | null;
  actor_id: number | null;
  actor_name: string | null;
  created_at: string;
}

export interface ReportSummary {
  id: number;
  report_number: string;
  partner_id: number;
  partner_name: string;
  project_id: number;
  project_code: string;
  project_name: string;
  fiscal_year: number;
  period: number;
  currency: string;
  status: ReportStatus;
  total_amount: Money;
  requires_review: boolean;
  open_exceptions: number;
  submitted_at: string | null;
  review_due_at: string | null;
  is_overdue: boolean;
  created_at: string;
}

export interface ReportDetail extends ReportSummary {
  partner_comment: string | null;
  submission_count: number;
  pm_approved_by_id: number | null;
  pm_approved_at: string | null;
  finance_approved_by_id: number | null;
  finance_approved_at: string | null;
  lines: ExpenseLine[];
  exceptions: VarianceException[];
  actions: ApprovalAction[];
  available_actions: string[];
}

export interface QueueItem extends ReportSummary {
  stage: "PM" | "FINANCE";
  highest_severity: Severity | null;
  exception_types: ExceptionType[];
  max_variance_pct: string | null;
}

export interface VarianceRow {
  cost_category_id: number;
  cost_category_name: string | null;
  gl_account_id: number;
  gl_account_number: string | null;
  planned: Money;
  actual: Money;
  variance: Money;
  variance_pct: string | null;
  ytd_planned: Money;
  ytd_actual: Money;
  ytd_variance: Money;
  annual_planned: Money;
  remaining_budget: Money;
  has_plan_line: boolean;
  within_tolerance: boolean;
  rule_name: string | null;
  reason: string;
}

export interface VarianceResult {
  report_id: number;
  rows: VarianceRow[];
  findings: { exception_type: ExceptionType; severity: Severity; message: string; line_id: number | null }[];
  totals: Record<string, string | boolean | null>;
  auto_accept: boolean;
}

export interface DashboardSummary {
  fiscal_year: number;
  planned_total: Money;
  actual_booked: Money;
  actual_pending_review: Money;
  variance: Money;
  utilization_pct: string | null;
  remaining_budget: Money;
  status_counts: Record<ReportStatus, number>;
  pending_pm_review: number;
  pending_finance_review: number;
  overdue_reviews: number;
  open_exceptions: number;
  over_budget_projects: number;
}

export interface PeriodPoint {
  period: number;
  planned: Money;
  actual: Money;
  pending: Money;
  variance: Money;
  variance_pct: string | null;
  ytd_planned: Money;
  ytd_actual: Money;
  ytd_variance: Money;
}

export interface EntityTotals {
  id: number;
  code: string;
  name: string;
  planned: Money;
  actual: Money;
  pending: Money;
  variance: Money;
  utilization_pct: string | null;
  remaining_budget: Money;
  over_budget: boolean;
}

export interface TopVariance {
  exception_id: number;
  report_id: number;
  report_number: string;
  partner_name: string;
  project_code: string;
  period: number;
  cost_category: string | null;
  gl_account: string | null;
  planned: Money;
  actual: Money;
  variance: Money;
  variance_pct: string | null;
  severity: Severity;
  exception_status: string;
  report_status: ReportStatus;
}

export interface BudgetVersion {
  id: number;
  version_no: number;
  status: "DRAFT" | "ACTIVE" | "SUPERSEDED";
  change_reason: string;
  total_amount: Money;
  created_by_id: number | null;
  approved_by_id: number | null;
  approved_at: string | null;
  created_at: string;
}

export interface BudgetLine {
  id: number;
  period: number;
  cost_category_id: number;
  cost_category_name: string;
  gl_account_id: number;
  gl_account_number: string;
  planned_amount: Money;
}

export interface BudgetPlan {
  id: number;
  partner_id: number;
  partner_name: string;
  project_id: number;
  project_code: string;
  project_name: string;
  fiscal_year: number;
  currency: string;
  name: string;
  active_version_no: number | null;
  active_total: Money | null;
  versions: BudgetVersion[];
}

export interface AuditLog {
  id: number;
  entity_type: string;
  entity_id: string;
  action: string;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  comment: string | null;
  actor_id: number | null;
  actor_email: string | null;
  actor_roles: string | null;
  request_id: string | null;
  created_at: string;
}

export interface ToleranceRule {
  id: number;
  name: string;
  description: string | null;
  partner_id: number | null;
  project_id: number | null;
  cost_category_id: number | null;
  max_variance_pct: string;
  max_variance_abs: Money;
  abs_currency: string;
  direction: "BOTH" | "OVERSPEND_ONLY";
  priority: number;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
}

export interface Setting { key: string; value: unknown; description: string | null }

export interface ReportingPeriod {
  id: number;
  fiscal_year: number;
  period: number;
  start_date: string;
  end_date: string;
  submission_deadline: string;
  status: "OPEN" | "CLOSED";
}

export interface Notification {
  id: number;
  type: string;
  title: string;
  message: string;
  entity_type: string | null;
  entity_id: number | null;
  read_at: string | null;
  created_at: string;
}
