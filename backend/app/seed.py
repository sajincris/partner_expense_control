"""Demo data for Northbridge Humanitarian Fund (fictional).

Every report is pushed through the real workflow services, so statuses,
exceptions, approval journal and audit trail are produced exactly as in
production. Run:  python -m app.seed   (idempotent; --force to re-seed an empty DB check)
"""
import random
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.enums import PeriodStatus, ReviewDecision, RoleCode, VarianceDirection
from app.models import (
    BudgetPlanVersion,
    CostCategory,
    Currency,
    ExchangeRate,
    ExpenseReport,
    GLAccount,
    Partner,
    Project,
    ProjectPartner,
    ReportingPeriod,
    Role,
    ToleranceRule,
)
from app.schemas.budget import BudgetLineIn, BudgetPlanCreate, BudgetVersionCreate
from app.schemas.expense import ExpenseLineIn, ExpenseReportCreate
from app.services import budget_service, report_service, user_service
from app.services.audit import set_audit_context
from app.services.settings_service import ensure_defaults
from app.workflows import report_workflow as wf

DEMO_PASSWORD = "Demo@2026!"  # demo only - documented in README
FY = 2026
RNG = random.Random(2026)
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"

ROLES = [
    (RoleCode.PARTNER, "Partner", "Submits monthly expense reports for own organisation"),
    (RoleCode.PROJECT_MANAGER, "Project Manager", "Reviews business justification of variance exceptions"),
    (RoleCode.FINANCE_OFFICER, "Finance Officer", "Validates budget, accounting and documents; final approver"),
    (RoleCode.FINANCE_LEAD, "Finance Lead / Administrator", "Configures rules, users, periods; activates budgets"),
    (RoleCode.AUDITOR, "Auditor / Viewer", "Read-only access to reports, exceptions and audit trail"),
]

CATEGORIES = [  # code, name, GL, GL name
    ("PERS", "Personnel", "6100", "Salaries and benefits"),
    ("TRAV", "Travel and transport", "6200", "Travel and per diem"),
    ("SUPP", "Supplies and commodities", "6300", "Programme supplies"),
    ("EQUP", "Equipment", "6400", "Equipment and assets < USD 5,000"),
    ("SERV", "Contractual services", "6500", "Contractual services"),
    ("OPER", "Operating costs", "6600", "Office rent and utilities"),
    ("VISB", "Visibility and communication", "6700", "Visibility materials"),
]

# Monthly plan per partner/project (USD) by category code. VISB is deliberately never planned.
PLANS = {
    ("HBA", "WASH-2026"): {"PERS": 8000, "TRAV": 1200, "SUPP": 4500, "EQUP": 3000, "SERV": 2500, "OPER": 900},
    ("DCH", "HLT-2026"): {"PERS": 14000, "TRAV": 2200, "SUPP": 6000, "SERV": 1800, "OPER": 1100},
    ("GVW", "EDU-2026"): {"PERS": 6500, "TRAV": 800, "SUPP": 3200, "SERV": 1500, "OPER": 700},
    ("HBA", "EDU-2026"): {"PERS": 3000, "TRAV": 400, "SUPP": 1500, "OPER": 300},
}

# (scenario, outcome) per period. Scenarios: ok | over | noplan | dup | nodoc
SCENARIOS = {
    ("HBA", "WASH-2026"): {1: ("ok", None), 2: ("ok", None), 3: ("over", "approved"), 4: ("ok", None), 5: ("nodoc", "approved"),
                           6: ("ok", None), 7: ("over", "rejected_fin"), 8: ("ok", None), 9: ("dup", "returned"),
                           10: ("over", "pending_pm_overdue")},
    ("DCH", "HLT-2026"): {1: ("ok", None), 2: ("over_pers", "approved"), 3: ("ok", None), 4: ("noplan", "rejected_pm"),
                          5: ("ok", None), 6: ("ok", None), 7: ("over", "returned_then_approved"), 8: ("ok", None),
                          9: ("over", "pending_fin"), 10: ("ok", "draft")},
    ("GVW", "EDU-2026"): {1: ("ok", None), 2: ("ok", None), 3: ("ok", None), 4: ("over", "approved"), 5: ("ok", None),
                          6: ("ok", None), 7: ("ok", None), 8: ("noplan", "approved"), 9: ("over", "pending_pm"),
                          10: ("ok", None)},
    ("HBA", "EDU-2026"): {1: ("ok", None), 2: ("ok", None), 3: ("ok", None), 4: ("ok", None), 5: ("over", "approved"),
                          6: ("ok", None), 7: ("ok", None), 8: ("ok", None), 9: ("nodoc", "pending_fin_overdue"),
                          10: ("ok", "cancelled")},
}

PM_APPROVE = [
    "Additional hygiene kits procured after the October flood response; quantities confirmed in distribution lists.",
    "Overspend explained by fuel price increase for mobile clinic vehicles; activity targets were met.",
    "Unplanned spend is eligible under the agreement; will be covered from savings on equipment in Q4.",
]
FIN_APPROVE = "Budget available in annual envelope; GL coding verified; invoices and proof of payment on file."


def _now() -> datetime:
    return datetime.now(UTC)


def _dt(d: date, hour: int = 10) -> datetime:
    return datetime(d.year, d.month, d.day, hour, tzinfo=UTC)


def seed(db: Session) -> None:
    if db.scalars(select(Role)).first():
        print("Database already seeded - nothing to do.")
        return

    # ------------------------------------------------------------ reference data
    db.add_all([Currency(code="USD", name="US Dollar"), Currency(code="EUR", name="Euro"), Currency(code="MDL", name="Moldovan Leu")])
    db.flush()
    db.add_all([
        ExchangeRate(from_currency="EUR", to_currency="USD", rate=Decimal("1.08000000"), rate_date=date(FY, 1, 1), source="Demo"),
        ExchangeRate(from_currency="MDL", to_currency="USD", rate=Decimal("0.05650000"), rate_date=date(FY, 1, 1), source="Demo"),
    ])
    roles = {}
    for code, name, desc in ROLES:
        roles[code] = Role(code=code, name=name, description=desc)
        db.add(roles[code])
    cats, gls = {}, {}
    for code, name, gl, gl_name in CATEGORIES:
        cats[code] = CostCategory(code=code, name=name)
        db.add(cats[code])
        db.flush()
        gls[code] = GLAccount(account_number=gl, name=gl_name, cost_category_id=cats[code].id)
        db.add(gls[code])
    ensure_defaults(db)
    db.flush()

    # ------------------------------------------------------------ partners & users
    partners = {
        "HBA": Partner(code="HBA", name="Hope Bridge Association", registration_number="1012600011223", country="MD", contact_email="finance@hopebridge.example"),
        "DCH": Partner(code="DCH", name="Danube Community Health", registration_number="RO-44871203", country="RO", contact_email="accounts@danubehealth.example"),
        "GVW": Partner(code="GVW", name="Green Valley Learning Initiative", registration_number="UA-39201177", country="UA", contact_email="office@greenvalley.example"),
    }
    db.add_all(partners.values())
    db.flush()

    def mk(email, name, role_codes, partner=None):
        return user_service.create_user(db, email=email, full_name=name, password=DEMO_PASSWORD, roles=set(role_codes),
                                        partner_id=partner.id if partner else None, actor=None)

    admin = mk("admin@demo.local", "Elena Varga", [RoleCode.FINANCE_LEAD])
    fin1 = mk("finance@demo.local", "Daniel Okafor", [RoleCode.FINANCE_OFFICER])
    fin2 = mk("finance2@demo.local", "Sofia Lindqvist", [RoleCode.FINANCE_OFFICER])
    pm_wash = mk("pm.wash@demo.local", "Marco Bianchi", [RoleCode.PROJECT_MANAGER])
    pm_health = mk("pm.health@demo.local", "Amina Diallo", [RoleCode.PROJECT_MANAGER])
    mk("auditor@demo.local", "Thomas Keller", [RoleCode.AUDITOR])
    partner_users = {
        "HBA": mk("partner.hba@demo.local", "Ana Cojocaru", [RoleCode.PARTNER], partners["HBA"]),
        "DCH": mk("partner.dch@demo.local", "Mihai Stan", [RoleCode.PARTNER], partners["DCH"]),
        "GVW": mk("partner.gvw@demo.local", "Olena Kovalenko", [RoleCode.PARTNER], partners["GVW"]),
    }
    set_audit_context(db, user=admin)

    # ------------------------------------------------------------ projects
    projects = {
        "WASH-2026": Project(code="WASH-2026", name="Clean Water for Rural Schools", donor="Global Relief Trust",
                             start_date=date(FY, 1, 1), end_date=date(FY + 1, 6, 30), currency="USD", project_manager_id=pm_wash.id),
        "HLT-2026": Project(code="HLT-2026", name="Mobile Primary Health Clinics", donor="European Health Partnership Fund",
                            start_date=date(FY, 1, 1), end_date=date(FY, 12, 31), currency="USD", project_manager_id=pm_health.id),
        "EDU-2026": Project(code="EDU-2026", name="Learning Continuity for Displaced Children", donor="Global Relief Trust",
                            start_date=date(FY, 1, 1), end_date=date(FY + 1, 12, 31), currency="USD", project_manager_id=pm_wash.id),
    }
    db.add_all(projects.values())
    db.flush()
    for (pcode, prj) in PLANS:
        db.add(ProjectPartner(project_id=projects[prj].id, partner_id=partners[pcode].id,
                              agreement_reference=f"PA-{prj}-{pcode}", start_date=date(FY, 1, 1)))

    # ------------------------------------------------------------ reporting periods
    for m in range(1, 13):
        start = date(FY, m, 1)
        end = date(FY + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        db.add(ReportingPeriod(fiscal_year=FY, period=m, start_date=start, end_date=end,
                               submission_deadline=end + timedelta(days=15), status=PeriodStatus.OPEN))

    # ------------------------------------------------------------ tolerance rules
    db.add_all([
        ToleranceRule(name="Global default", description="Auto-accept when overspend <= 5% and <= USD 500 per category/GL line.",
                      max_variance_pct=Decimal("5"), max_variance_abs=Decimal("500.00"), abs_currency="USD",
                      direction=VarianceDirection.OVERSPEND_ONLY, priority=100, effective_from=date(FY, 1, 1)),
        ToleranceRule(name="Health project payroll - strict", description="Donor requires approval of any payroll overspend above 3% / USD 300.",
                      project_id=projects["HLT-2026"].id, cost_category_id=cats["PERS"].id, max_variance_pct=Decimal("3"),
                      max_variance_abs=Decimal("300.00"), abs_currency="USD", direction=VarianceDirection.OVERSPEND_ONLY,
                      priority=10, effective_from=date(FY, 1, 1)),
        ToleranceRule(name="Equipment - absolute cap", description="Equipment overspend reviewed above USD 250 regardless of %.",
                      cost_category_id=cats["EQUP"].id, max_variance_pct=Decimal("10"), max_variance_abs=Decimal("250.00"),
                      abs_currency="USD", direction=VarianceDirection.OVERSPEND_ONLY, priority=50, effective_from=date(FY, 1, 1)),
    ])
    db.flush()

    # ------------------------------------------------------------ budget plans (maker: finance officer, checker: finance lead)
    for (pcode, prj), monthly in PLANS.items():
        lines = [BudgetLineIn(period=m, cost_category_id=cats[c].id, gl_account_id=gls[c].id, planned_amount=Decimal(amount))
                 for m in range(1, 13) for c, amount in monthly.items()]
        set_audit_context(db, user=fin1)
        plan = budget_service.create_plan(db, BudgetPlanCreate(
            partner_id=partners[pcode].id, project_id=projects[prj].id, fiscal_year=FY, currency="USD",
            name=f"{prj} / {partners[pcode].name} FY{FY}",
            initial_version=BudgetVersionCreate(change_reason="Initial approved budget per partner agreement", lines=lines)), fin1)
        set_audit_context(db, user=admin)
        budget_service.activate_version(db, plan.id, plan.versions[0].id, admin)
        if (pcode, prj) == ("DCH", "HLT-2026"):
            # Reforecast: supplies +10% from July after donor amendment no. 1.
            relines = [BudgetLineIn(period=ln.period, cost_category_id=ln.cost_category_id, gl_account_id=ln.gl_account_id,
                                    planned_amount=(ln.planned_amount * Decimal("1.10")).quantize(Decimal("0.01"))
                                    if ln.cost_category_id == cats["SUPP"].id and ln.period >= 7 else ln.planned_amount)
                       for ln in lines]
            set_audit_context(db, user=fin2)
            v2 = budget_service.create_version(db, plan.id, BudgetVersionCreate(
                change_reason="Donor amendment no. 1: medical supplies +10% from July", lines=relines), fin2)
            set_audit_context(db, user=admin)
            budget_service.activate_version(db, plan.id, v2.id, admin)
    db.flush()

    # ------------------------------------------------------------ expense reports through the real workflow
    pms = {"WASH-2026": pm_wash, "HLT-2026": pm_health, "EDU-2026": pm_wash}
    invoice_log: dict[tuple, list[str]] = {}
    for (pcode, prj), periods in SCENARIOS.items():
        puser = partner_users[pcode]
        project = projects[prj]
        for period, (scenario, outcome) in periods.items():
            submit_at = _dt(date(FY, period, 28) + timedelta(days=10))
            if outcome in ("pending_pm", "pending_fin"):
                submit_at = _now() - timedelta(hours=20)
            elif outcome in ("pending_pm_overdue", "pending_fin_overdue"):
                submit_at = _now() - timedelta(days=9)

            set_audit_context(db, user=puser)
            report = report_service.create_report(db, ExpenseReportCreate(project_id=project.id, fiscal_year=FY, period=period,
                                                                           currency="USD"), puser)
            refs = _add_lines(db, report, puser, pcode, prj, period, scenario, cats, gls, invoice_log)
            invoice_log[(pcode, prj, period)] = refs
            db.expire(report)

            if outcome == "draft":
                continue
            if outcome == "cancelled":
                wf.cancel_report(db, report, puser, "Duplicate draft created by mistake - cancelled by partner.")
                continue

            wf.submit_report(db, report, puser, now=submit_at)
            if outcome is None or report.status.value == "AUTO_ACCEPTED":
                continue
            pm = pms[prj]
            fin = fin1 if period % 2 else fin2
            t_pm, t_fin = submit_at + timedelta(days=1), submit_at + timedelta(days=2)

            def pm_do(decision, comment, at=t_pm, report=report, pm=pm):
                set_audit_context(db, user=pm)
                wf.pm_review(db, report, pm, decision, comment, now=at)

            def fin_do(decision, comment, at=t_fin, ok=True, report=report, fin=fin):
                set_audit_context(db, user=fin)
                wf.finance_review(db, report, fin, decision, comment,
                                  checklist={"budget_available": ok, "accounting_treatment_ok": ok, "documents_ok": ok}, now=at)

            if outcome == "approved":
                pm_do(ReviewDecision.APPROVE, RNG.choice(PM_APPROVE))
                fin_do(ReviewDecision.APPROVE, FIN_APPROVE)
            elif outcome == "rejected_fin":
                pm_do(ReviewDecision.APPROVE, "Activity was implemented; partner states supplier price increase.")
                fin_do(ReviewDecision.REJECT, "Procurement threshold exceeded without three quotations; cost ineligible under the agreement.", ok=False)
            elif outcome == "rejected_pm":
                pm_do(ReviewDecision.REJECT, "Visibility materials are not part of the approved workplan; expense not eligible.")
            elif outcome == "returned":
                pm_do(ReviewDecision.RETURN, "Invoice reference repeats an invoice reported in August. Please correct or explain.")
            elif outcome == "returned_then_approved":
                fin_do_return_at = t_fin
                pm_do(ReviewDecision.APPROVE, "Additional outreach days agreed with the donor focal point.")
                fin_do(ReviewDecision.RETURN, "Please attach the signed timesheets supporting the extra outreach days.", at=fin_do_return_at)
                set_audit_context(db, user=puser)
                wf.submit_report(db, report, puser, comment="Signed timesheets attached; amounts unchanged.",
                                 now=submit_at + timedelta(days=4))
                pm_do(ReviewDecision.APPROVE, "Timesheets confirm outreach days; justification accepted.", at=submit_at + timedelta(days=5))
                fin_do(ReviewDecision.APPROVE, FIN_APPROVE, at=submit_at + timedelta(days=6))
            elif outcome == "pending_fin" or outcome == "pending_fin_overdue":
                pm_do(ReviewDecision.APPROVE, "Variance justified by scale-up of activities in the reporting month.", at=submit_at + timedelta(hours=3))
            # pending_pm / pending_pm_overdue: left in the PM queue

    # Close the first eight periods (books closed); 9-12 stay open.
    for rp in db.scalars(select(ReportingPeriod).where(ReportingPeriod.fiscal_year == FY, ReportingPeriod.period <= 8)).all():
        rp.status = PeriodStatus.CLOSED
    db.commit()

    counts = {}
    for r in db.scalars(select(ExpenseReport)).all():
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    versions = db.scalars(select(BudgetPlanVersion)).all()
    print(f"Seed complete: {len(versions)} budget versions, reports by status: {dict(sorted(counts.items()))}")
    print(f"Demo password for all users: {DEMO_PASSWORD}")


def _add_lines(db, report, puser, pcode, prj, period, scenario, cats, gls, invoice_log) -> list[str]:
    monthly = PLANS[(pcode, prj)]
    refs: list[str] = []
    seq = 0
    exp_date = date(FY, period, 20)
    for code, planned in monthly.items():
        factor = Decimal(str(round(RNG.uniform(0.96, 1.02), 4)))
        if scenario == "over" and code == "SUPP":
            factor = Decimal("1.18")
        if scenario == "over_pers" and code == "PERS":
            factor = Decimal("1.045")
        amount = (Decimal(planned) * factor).quantize(Decimal("0.01"))
        parts = [amount] if amount < 3000 else [(amount * Decimal("0.6")).quantize(Decimal("0.01")),
                                                 amount - (amount * Decimal("0.6")).quantize(Decimal("0.01"))]
        for part in parts:
            seq += 1
            ref = f"{pcode}-{prj[:3]}-{period:02d}{seq:03d}"
            if scenario == "dup" and seq == 1:
                ref = invoice_log[(pcode, prj, period - 1)][0]  # re-used invoice from the previous month
            line = report_service.add_line(db, report, ExpenseLineIn(
                expense_date=exp_date, cost_category_id=cats[code].id, gl_account_id=gls[code].id,
                description=f"{cats[code].name} - {_month(period)} {FY}", amount=part, currency="USD", invoice_reference=ref), puser)
            refs.append(ref)
            if not (scenario == "nodoc" and code == "TRAV"):
                report_service.upload_attachment(db, report, line.id, data=PDF, filename=f"{ref}.pdf",
                                                 content_type="application/pdf", actor=puser)
    if scenario == "noplan":
        seq += 1
        ref = f"{pcode}-{prj[:3]}-{period:02d}{seq:03d}"
        line = report_service.add_line(db, report, ExpenseLineIn(
            expense_date=exp_date, cost_category_id=cats["VISB"].id, gl_account_id=gls["VISB"].id,
            description="Banners and branded T-shirts for community event", amount=Decimal("640.00"), currency="USD",
            invoice_reference=ref), puser)
        report_service.upload_attachment(db, report, line.id, data=PDF, filename=f"{ref}.pdf", content_type="application/pdf", actor=puser)
        refs.append(ref)
    return refs


def _month(m: int) -> str:
    return ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][m - 1]


def main() -> None:
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
