# API reference

Base URL: `http://localhost:8000/api/v1` · Interactive docs: **`/docs`** (Swagger UI) and **`/redoc`**.
All endpoints except login require `Authorization: Bearer <token>`.

**Conventions**

* Money is sent and returned as decimal strings with 2 decimals (`"10450.00"`).
* List endpoints are paginated: `?page=1&size=25&sort=-created_at` → `{items, total, page, size, pages}`.
* Errors always use one envelope:

```json
{ "error": { "code": "INVALID_STATUS_TRANSITION", "message": "Action APPROVE is not allowed when the report is APPROVED.", "details": { "allowed_actions": [] } } }
```

| HTTP | `code` examples |
|---|---|
| 401 | `UNAUTHENTICATED` |
| 403 | `FORBIDDEN`, `SEGREGATION_OF_DUTIES` |
| 404 | `NOT_FOUND` (also for records outside your scope) |
| 409 | `INVALID_STATUS_TRANSITION`, `CONFLICT`, `INTEGRITY_CONSTRAINT` |
| 422 | `REQUEST_VALIDATION_FAILED`, `SUBMISSION_INVALID`, `REPORT_LOCKED`, `COMMENT_REQUIRED`, `FINANCE_CHECKLIST_INCOMPLETE`, `PM_APPROVAL_MISSING`, `NO_ACTIVE_PLAN` |

## Endpoints

| Method | Path | Roles | Description |
|---|---|---|---|
| POST | `/auth/login` | public | OAuth2 password form (Swagger) |
| POST | `/auth/token` | public | JSON login → JWT |
| GET | `/auth/me` | any | Current user and roles |
| GET | `/roles` | Lead, Auditor | Role catalogue |
| GET/POST | `/users` | Lead (write), Auditor (read) | List (filter `q`, `role`, `partner_id`, `is_active`) / create |
| GET/PATCH | `/users/{id}` | Lead | Read / update (name, active, partner) |
| PUT | `/users/{id}/roles` | Lead | Replace roles (SoD-checked) |
| GET | `/master/cost-categories`, `/master/gl-accounts`, `/master/currencies` | any | Reference data |
| GET/POST | `/partners` | any (scoped) / Lead | List / create |
| GET/PATCH/DELETE | `/partners/{id}` | scoped / Lead / Lead | Read / update / soft delete |
| GET/POST | `/projects` | any (scoped) / Lead | List / create |
| GET/PATCH | `/projects/{id}` | internal / Lead | Read / update |
| POST | `/projects/{id}/partners` | Lead | Link implementing partner |
| GET/POST | `/budget-plans` | scoped / Finance | List / create plan with first DRAFT version |
| POST | `/budget-plans/import` | Finance | CSV upload → DRAFT versions (all-or-nothing) |
| GET | `/budget-plans/{id}` | scoped | Plan with versions |
| GET | `/budget-plans/{id}/versions/{vid}` | scoped | Version with lines |
| POST | `/budget-plans/{id}/versions` | Finance | New DRAFT version (reforecast) — reason mandatory |
| POST | `/budget-plans/{id}/versions/{vid}/activate` | Lead (≠ creator) | Activate; previous ACTIVE → SUPERSEDED |
| GET/POST | `/expense-reports` | scoped / Partner | List (filters `status[]`, `fiscal_year`, `period`, `partner_id`, `project_id`, `overdue`) / create draft |
| GET | `/expense-reports/{id}` | scoped | Detail: lines, exceptions, journal, `available_actions` |
| GET | `/expense-reports/{id}/variance` | scoped | Plan vs actual calculation (live preview for drafts) |
| POST | `/expense-reports/{id}/lines` | Partner (owner) | Add line (DRAFT/RETURNED only) |
| PATCH/DELETE | `/expense-reports/{id}/lines/{line_id}` | Partner (owner) | Update / soft-delete line |
| POST | `/expense-reports/{id}/attachments` | Partner (owner) | Multipart upload (`file`, optional `line_id`) |
| GET | `/expense-reports/{id}/attachments/{aid}/download` | scoped | Download document |
| POST | `/expense-reports/{id}/submit` | Partner (owner) | Submit / resubmit (`comment` mandatory on resubmit) |
| POST | `/expense-reports/{id}/cancel` | Partner (owner) | Cancel draft or returned report |
| GET | `/reviews/queue` | PM, Finance, Lead, Auditor | Exception queue (`stage=PM|FINANCE`, `overdue`, `project_id`, `partner_id`) |
| POST | `/expense-reports/{id}/pm-review` | assigned PM | `{decision, comment}` |
| POST | `/expense-reports/{id}/finance-review` | Finance Officer | `{decision, comment, checklist}` |
| GET | `/dashboard/summary` | any (scoped) | KPIs, status counts, overdue, over-budget projects |
| GET | `/dashboard/plan-vs-actual` | any (scoped) | 12-month series incl. YTD (filters `project_id`, `partner_id`) |
| GET | `/dashboard/projects`, `/dashboard/partners` | any (scoped) | Planned / actual / pending / utilisation |
| GET | `/dashboard/top-variances` | any (scoped) | Largest variance exceptions |
| GET | `/reports/monthly-variance` | any (scoped) | `format=json|csv|xlsx` |
| GET | `/reports/expense-reports/export` | any (scoped) | Register export, filter `status[]` |
| GET | `/reports/top-variances/export` | internal | CSV/XLSX |
| GET | `/audit-logs` | Finance, Lead, Auditor, PM | Filters `entity_type`, `entity_id`, `action`, `actor_id`, `date_from`, `date_to` |
| GET/POST | `/config/tolerance-rules` | Finance/Auditor (read), Lead (write) | Rules |
| PATCH | `/config/tolerance-rules/{id}` | Lead | Update — `change_reason` mandatory |
| GET | `/config/settings` | Finance, Lead, Auditor | Workflow settings |
| PUT | `/config/settings/{key}` | Lead | Change — `change_reason` mandatory |
| GET/POST/PATCH | `/config/reporting-periods` | any / Lead | Fiscal calendar, open/close |
| GET | `/notifications` · POST `/notifications/{id}/read` | any | In-app notifications |
| GET | `/health` | public | Liveness |

## Examples

### Login

```http
POST /api/v1/auth/token
Content-Type: application/json

{ "email": "partner.hba@demo.local", "password": "Demo@2026!" }
```

```json
{ "access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in": 28800,
  "user": { "id": 7, "email": "partner.hba@demo.local", "full_name": "Ana Cojocaru", "partner_id": 1, "partner_name": "Hope Bridge Association", "roles": ["PARTNER"] } }
```

### Create a report, add a line, upload a document

```http
POST /api/v1/expense-reports
{ "project_id": 1, "fiscal_year": 2026, "period": 11, "currency": "USD" }

POST /api/v1/expense-reports/42/lines
{ "expense_date": "2026-11-20", "cost_category_id": 3, "gl_account_id": 3,
  "description": "Hygiene kits - November", "amount": "5310.00", "currency": "USD", "invoice_reference": "INV-2026-1188" }

POST /api/v1/expense-reports/42/attachments   (multipart: file=@invoice.pdf, line_id=311)
```

### Variance preview

```http
GET /api/v1/expense-reports/42/variance
```

```json
{
  "report_id": 42,
  "rows": [
    { "cost_category_id": 3, "cost_category_name": "Supplies and commodities", "gl_account_number": "6300",
      "planned": "4500.00", "actual": "5310.00", "variance": "810.00", "variance_pct": "18.00",
      "ytd_planned": "49500.00", "ytd_actual": "50132.40", "ytd_variance": "632.40",
      "annual_planned": "54000.00", "remaining_budget": "3867.60", "has_plan_line": true,
      "within_tolerance": false, "rule_name": "Global default",
      "reason": "Outside tolerance: 18.00% > 5.0000% and 810.00 > 500.00 USD." }
  ],
  "findings": [ { "exception_type": "VARIANCE_OVER_TOLERANCE", "severity": "HIGH", "message": "Outside tolerance: ...", "line_id": null } ],
  "totals": { "total_planned": "20100.00", "total_actual": "20955.12", "auto_accept": false, "project_over_budget": false },
  "auto_accept": false
}
```

### Submit → routed to PM

```http
POST /api/v1/expense-reports/42/submit
{ "comment": "Additional kits for the flood response, see distribution list." }
```

Response (abridged): `"status": "PENDING_PM_REVIEW"`, `"review_due_at": "2026-11-26T10:00:00Z"`,
`"actions": [{"action": "SUBMIT"}, {"action": "ROUTE_TO_PM", "actor_name": "System"}]`.

### PM approval, then Finance final approval

```http
POST /api/v1/expense-reports/42/pm-review
{ "decision": "APPROVE", "comment": "Extra kits agreed with the donor focal point on 12 Nov." }

POST /api/v1/expense-reports/42/finance-review
{ "decision": "APPROVE", "comment": "Budget available; GL 6300 correct; invoices on file.",
  "checklist": { "budget_available": true, "accounting_treatment_ok": true, "documents_ok": true } }
```

### Typical rejections

```json
{ "error": { "code": "INVALID_STATUS_TRANSITION",
  "message": "Cannot APPROVE at this stage: report is PENDING_PM_REVIEW, expected PENDING_FINANCE_REVIEW.",
  "details": { "status": "PENDING_PM_REVIEW", "expected": "PENDING_FINANCE_REVIEW" } } }
```

```json
{ "error": { "code": "SEGREGATION_OF_DUTIES",
  "message": "Four-eyes principle: the PM approver cannot also give the Finance approval.", "details": {} } }
```
