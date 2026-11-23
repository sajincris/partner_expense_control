# User stories and acceptance criteria

Format: *As a … I want … so that …*, followed by Given/When/Then criteria. `[T]` marks criteria covered by automated tests.

## Epic 1 — Partner reporting

**US-01 Create a monthly report.** As a partner accountant I want to open a draft report for a project and month so that I can enter my expenses.
- Given I belong to a partner linked to the project, when I create a report for an open period, then a DRAFT with a report number is created.
- Given a live report already exists for that project and month, then creation is refused with 409 and the existing report id.
- Given I am not a partner user, then I get 403. `[T]`

**US-02 Enter expense lines with documents.** As a partner accountant I want to add lines with category, GL, invoice reference and a scanned invoice so that reviewers can verify them.
- Amount must be > 0 with at most 2 decimals; the GL account must belong to the selected category.
- Uploads accept PDF/PNG/JPG/CSV/XLSX up to 10 MB; the SHA-256 is stored and the upload is audited.
- Lines can be changed only while the report is DRAFT or RETURNED (422 `REPORT_LOCKED` otherwise). `[T]`

**US-03 Preview before submitting.** As a partner I want to see the plan vs actual comparison and which exceptions will be raised so that I can justify them up front.
- The preview shows planned, actual, variance, %, YTD and remaining per category/GL and says "auto-accept" or "review required". `[T]`

**US-04 Submit.** As a partner I want to submit my report so that it is accepted or reviewed.
- Within tolerance and no other finding → AUTO_ACCEPTED immediately, partner notified. `[T]`
- Any finding → PENDING_PM_REVIEW with a due date; the assigned PM is notified. `[T]`
- Closed period, foreign currency line, date after period end, or (BLOCK policy) missing document → 422 with the list of errors. `[T]`

**US-05 Respond to a clarification request.** As a partner I want to correct a returned report and resubmit it with an explanation.
- The return comment is shown on the report; resubmission without a comment is refused. `[T]`
- On resubmission all checks run again; earlier exceptions become SUPERSEDED; earlier approvals no longer count. `[T]`

## Epic 2 — Variance control

**US-06 Configurable tolerance.** As the Finance Lead I want to define tolerance rules by scope so that policy changes need no release.
- A rule has max %, max amount, currency, direction, priority and validity dates; the most specific active rule applies. `[T]`
- Every rule change requires a reason and appears in the audit trail. `[T]`
- If no rule applies, the report goes to manual review. `[T]`

**US-07 Control checks.** As Finance I want duplicate invoices, unplanned spending, missing documents and annual overruns flagged automatically.
- Same invoice reference in the report or in another live report of the partner/project → DUPLICATE_INVOICE. `[T]`
- Spending on a category/GL with no plan line in the year → NO_PLAN_LINE. `[T]`
- Cumulative actuals above the annual plan → OVER_ANNUAL_BUDGET and the project is flagged on dashboards. `[T]`

## Epic 3 — Review and approval

**US-08 Exception queue.** As a PM or Finance Officer I want a queue of reports waiting for me, sorted by due date, with severity and exception types, so that I work on the most urgent first.
- PMs see only their projects; overdue items are highlighted and can be filtered.

**US-09 PM review.** As the project's PM I want to approve, reject or return an exception with a mandatory justification.
- Only the PM assigned to the project can act; others do not see the report (404). `[T]`
- Approval moves the report to PENDING_FINANCE_REVIEW and stores my justification on each open exception. `[T]`

**US-10 Finance validation.** As a Finance Officer I want to confirm budget availability, accounting treatment and documents before the final approval.
- Approval requires a prior PM approval, all three checklist confirmations and a comment. `[T]`
- I cannot approve a report whose PM approval I gave myself (four-eyes). Finance cannot skip the PM step (409). `[T]`
- Reject is final; return sends the report back to the partner. `[T]`

## Epic 4 — Budgets

**US-11 Upload and version budgets.** As a Finance Officer I want to upload plans from CSV and create reforecast versions with a reason.
- Invalid CSV rows reject the whole file with row-level messages.
- A new version is DRAFT until a Finance Lead other than its creator activates it; the previous version becomes SUPERSEDED.

## Epic 5 — Oversight

**US-12 Plan vs actual dashboard.** As management I want KPIs, monthly plan vs actual (with YTD) and utilisation per project and partner.
- Only booked (accepted/approved) spend counts as actual; amounts under review are shown separately. `[T]`

**US-13 Reports and exports.** As Finance I want the monthly variance report, the report register and top variances in Excel/CSV.
- Exports respect my data scope and are recorded in the audit trail. `[T]`

**US-14 Audit trail.** As an auditor I want to see who changed what, when, with old and new values, and I want this record to be tamper-proof.
- Every change to financial data is logged automatically with old/new values. `[T]`
- The audit log and approval journal cannot be updated or deleted, even directly in the database (CI-verified).

**US-15 Access control.** As the Finance Lead I want role-based access with segregation of duties.
- Conflicting role combinations are refused; administrators cannot change their own roles. `[T]`
- Auditors are read-only everywhere. `[T]`
