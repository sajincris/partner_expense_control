# Data model (ERD)

PostgreSQL 16, normalised to 3NF. Money: `NUMERIC(18,2)`; FX rates `NUMERIC(18,8)`; percentages `NUMERIC(9,4)`.
Enumerations are native PostgreSQL ENUM types. Migration: `backend/alembic/versions/20261123_0001_initial_schema.py`.

```mermaid
erDiagram
    users ||--o{ user_roles : has
    roles ||--o{ user_roles : grants
    partners |o--o{ users : "employs (partner users)"
    users |o--o{ projects : "manages (PM)"
    projects ||--o{ project_partners : "implemented by"
    partners ||--o{ project_partners : implements
    currencies ||--o{ exchange_rates : "from / to"

    partners ||--o{ budget_plans : "planned for"
    projects ||--o{ budget_plans : "planned for"
    budget_plans ||--|{ budget_plan_versions : versions
    budget_plan_versions ||--|{ budget_plan_lines : lines
    cost_categories ||--o{ budget_plan_lines : classifies
    gl_accounts ||--o{ budget_plan_lines : "posts to"
    cost_categories ||--o{ gl_accounts : groups

    partners ||--o{ expense_reports : submits
    projects ||--o{ expense_reports : "reported on"
    budget_plan_versions |o--o{ expense_reports : "evaluated against"
    expense_reports ||--|{ expense_lines : contains
    budget_plan_lines |o--o{ expense_lines : "matched to"
    expense_reports ||--o{ expense_attachments : documents
    expense_lines |o--o{ expense_attachments : supports
    expense_reports ||--o{ variance_reviews : raises
    tolerance_rules |o--o{ variance_reviews : "applied in"
    expense_reports ||--o{ approval_actions : journal
    users |o--o{ approval_actions : acts
    users |o--o{ audit_logs : "acted in"
    users ||--o{ notifications : receives
    reporting_periods ||..o{ expense_reports : "fiscal_year + period"

    expense_reports {
        int id PK
        string report_number UK
        int partner_id FK
        int project_id FK
        int fiscal_year
        int period "1..12"
        enum status
        numeric total_amount "18,2"
        int submission_count
        int pm_approved_by_id FK
        int finance_approved_by_id FK
        timestamptz review_due_at
    }
    expense_lines {
        int id PK
        int report_id FK
        int line_no
        date expense_date
        int cost_category_id FK
        int gl_account_id FK
        numeric amount "> 0"
        string invoice_reference
        int matched_plan_line_id FK
        bool is_deleted
    }
    budget_plan_lines {
        int id PK
        int version_id FK
        int period
        int cost_category_id FK
        int gl_account_id FK
        numeric planned_amount ">= 0"
    }
    variance_reviews {
        int id PK
        int report_id FK
        enum exception_type
        enum severity
        enum status
        numeric planned_amount
        numeric actual_amount
        numeric variance_amount
        numeric variance_pct
        jsonb calculation_snapshot
    }
    audit_logs {
        int id PK
        string entity_type
        string entity_id
        string action
        jsonb old_values
        jsonb new_values
        int actor_id FK
        timestamptz created_at
    }
```

## Tables

| Table | Purpose | Key constraints |
|---|---|---|
| `users` | People who log in. Partner users carry `partner_id` (data scoping). Soft delete. | `email` unique |
| `roles` | PARTNER, PROJECT_MANAGER, FINANCE_OFFICER, FINANCE_LEAD, AUDITOR | `code` unique |
| `user_roles` | Many-to-many with `granted_by_id` | unique (user, role) |
| `partners` | Implementing partner organisations. Soft delete. | `code` unique |
| `projects` | Projects with donor, dates, currency and responsible PM. Soft delete. | `code` unique; `end_date >= start_date` |
| `project_partners` | Agreement linking a partner to a project | unique (project, partner) |
| `cost_categories` / `gl_accounts` | Chart of accounts; GL accounts map to one category | unique codes |
| `currencies` / `exchange_rates` | ISO-4217 currencies and dated FX rates | rate > 0; unique (pair, date); from ≠ to |
| `reporting_periods` | Fiscal calendar with deadlines and OPEN/CLOSED status | unique (year, period); period 1..12 |
| `budget_plans` | Plan header: partner × project × fiscal year | unique (partner, project, year) |
| `budget_plan_versions` | Versioned plan; DRAFT → ACTIVE → SUPERSEDED; reason, maker, checker | unique (plan, version_no); **partial unique: one ACTIVE per plan** |
| `budget_plan_lines` | Monthly planned amount per category/GL | unique (version, period, category, GL); amount ≥ 0 |
| `expense_reports` | Monthly report header and workflow state | **partial unique: one live report per partner/project/period**; `APPROVED ⇒ two distinct approvers` |
| `expense_lines` | Expense lines; soft delete; plan match | amount > 0; trigger locks lines outside DRAFT/RETURNED |
| `expense_attachments` | Supporting documents (storage key, SHA-256, size, MIME) | size > 0; storage key unique |
| `variance_reviews` | Exceptions raised by the engine, with calculation snapshot, PM justification, Finance note | indexed by report, status/type |
| `approval_actions` | Immutable workflow journal | append-only trigger |
| `tolerance_rules` | Configurable thresholds with scope, direction, priority, validity | limits ≥ 0; `effective_to >= effective_from` |
| `system_settings` | Key/value configuration (JSONB) | PK key |
| `audit_logs` | Append-only change log with old/new JSONB | append-only trigger; indexes on entity, actor, date |
| `notifications` | In-app notifications | index (user, read_at) |

## Design notes

* **Versioned plans, not edited plans.** A report stores `budget_plan_version_id`, and each exception stores a JSON
  calculation snapshot, so a decision can be explained later even after a reforecast.
* **Soft delete** on master data and expense lines keeps history; reports are never deleted (CANCELLED instead).
* **Partial unique indexes** encode business invariants (one ACTIVE version; one live report per period) in the database.
* **Surrogate integer keys** for simplicity; `report_number` (`ER-2026-00042`) is the business key shown to users.
* Indexes follow the query paths: queue (`status`, `review_due_at`), plan lookup (`version, category, GL`),
  duplicate detection (`invoice_reference`), audit (`entity_type, entity_id`, `created_at`).
