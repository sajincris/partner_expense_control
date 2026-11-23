"""Test fixtures.

Integration tests run the real FastAPI app against an in-memory SQLite database
(same models, same services). PostgreSQL-only objects (append-only triggers,
line-lock trigger) are covered by the Alembic migration and exercised in CI's
migration smoke step.
"""
import os
import tempfile
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("STORAGE_LOCAL_PATH", tempfile.mkdtemp(prefix="pec-test-"))

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

PASSWORD = "Test@Password1"


@pytest.fixture()
def engine():
    from app.models import Base

    eng = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def world(db):
    """Minimal but complete reference world. Returns a dict of ids."""
    from app.core.enums import PeriodStatus, RoleCode, VarianceDirection
    from app.models import (
        CostCategory,
        Currency,
        GLAccount,
        Partner,
        Project,
        ProjectPartner,
        ReportingPeriod,
        Role,
        ToleranceRule,
    )
    from app.schemas.budget import BudgetLineIn, BudgetPlanCreate, BudgetVersionCreate
    from app.services import budget_service, user_service
    from app.services.settings_service import ensure_defaults

    db.add(Currency(code="USD", name="US Dollar"))
    for code in RoleCode:
        db.add(Role(code=code, name=code.value.title()))
    pers, supp, visb = CostCategory(code="PERS", name="Personnel"), CostCategory(code="SUPP", name="Supplies"), CostCategory(code="VISB", name="Visibility")
    db.add_all([pers, supp, visb])
    db.flush()
    gl_pers = GLAccount(account_number="6100", name="Salaries", cost_category_id=pers.id)
    gl_supp = GLAccount(account_number="6300", name="Supplies", cost_category_id=supp.id)
    gl_visb = GLAccount(account_number="6700", name="Visibility", cost_category_id=visb.id)
    pa, pb = Partner(code="PA", name="Partner A"), Partner(code="PB", name="Partner B")
    db.add_all([gl_pers, gl_supp, gl_visb, pa, pb])
    ensure_defaults(db)
    db.flush()

    def mk(email, roles, partner=None):
        return user_service.create_user(db, email=email, full_name=email.split("@")[0], password=PASSWORD,
                                        roles=set(roles), partner_id=partner.id if partner else None, actor=None)

    users = {
        "partner_a": mk("partner.a@test.local", [RoleCode.PARTNER], pa),
        "partner_b": mk("partner.b@test.local", [RoleCode.PARTNER], pb),
        "pm": mk("pm@test.local", [RoleCode.PROJECT_MANAGER]),
        "pm_other": mk("pm.other@test.local", [RoleCode.PROJECT_MANAGER]),
        "fin": mk("fin@test.local", [RoleCode.FINANCE_OFFICER]),
        "fin2": mk("fin2@test.local", [RoleCode.FINANCE_OFFICER]),
        "admin": mk("admin@test.local", [RoleCode.FINANCE_LEAD]),
        "auditor": mk("auditor@test.local", [RoleCode.AUDITOR]),
    }
    project = Project(code="PRJ-1", name="Test project", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                      currency="USD", project_manager_id=users["pm"].id)
    db.add(project)
    db.flush()
    db.add_all([ProjectPartner(project_id=project.id, partner_id=pa.id), ProjectPartner(project_id=project.id, partner_id=pb.id)])
    for m in range(1, 13):
        start = date(2026, m, 1)
        end = date(2026 + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        db.add(ReportingPeriod(fiscal_year=2026, period=m, start_date=start, end_date=end, submission_deadline=end + timedelta(days=15),
                               status=PeriodStatus.OPEN))
    db.add(ToleranceRule(name="Global", max_variance_pct=Decimal("5"), max_variance_abs=Decimal("500"), abs_currency="USD",
                         direction=VarianceDirection.OVERSPEND_ONLY, effective_from=date(2026, 1, 1)))
    db.flush()
    lines = [BudgetLineIn(period=m, cost_category_id=c, gl_account_id=g, planned_amount=Decimal(a))
             for m in range(1, 13) for c, g, a in ((pers.id, gl_pers.id, "10000"), (supp.id, gl_supp.id, "2000"))]
    for partner in (pa, pb):
        plan = budget_service.create_plan(db, BudgetPlanCreate(
            partner_id=partner.id, project_id=project.id, fiscal_year=2026, name=f"Plan {partner.code}",
            initial_version=BudgetVersionCreate(change_reason="Initial budget", lines=lines)), users["fin"])
        budget_service.activate_version(db, plan.id, plan.versions[0].id, users["admin"])
    db.commit()
    return {
        "project_id": project.id, "partner_a": pa.id, "partner_b": pb.id,
        "pers": (pers.id, gl_pers.id), "supp": (supp.id, gl_supp.id), "visb": (visb.id, gl_visb.id),
        "users": {k: u.id for k, u in users.items()},
    }


@pytest.fixture()
def client(engine, world):
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def auth(client, email: str) -> dict:
    r = client.post("/api/v1/auth/token", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def h(client):
    """Lazy header factory: h('partner.a') -> auth headers."""
    cache: dict[str, dict] = {}

    def _h(name: str) -> dict:
        if name not in cache:
            cache[name] = auth(client, f"{name}@test.local")
        return cache[name]

    return _h
