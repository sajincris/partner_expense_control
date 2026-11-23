"""End-to-end API tests of the control workflow."""
API = "/api/v1"


def make_report(client, h, world, period, lines, attach=True, who="partner.a"):
    """lines: list of (category_key, amount, invoice_ref)."""
    r = client.post(f"{API}/expense-reports", json={"project_id": world["project_id"], "fiscal_year": 2026, "period": period},
                    headers=h(who))
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    for cat_key, amount, inv in lines:
        cat, gl = world[cat_key]
        lr = client.post(f"{API}/expense-reports/{rid}/lines", headers=h(who), json={
            "expense_date": f"2026-{period:02d}-15", "cost_category_id": cat, "gl_account_id": gl,
            "description": f"Test line {inv}", "amount": str(amount), "currency": "USD", "invoice_reference": inv})
        assert lr.status_code == 201, lr.text
        if attach:
            up = client.post(f"{API}/expense-reports/{rid}/attachments", headers=h(who), data={"line_id": str(lr.json()["id"])},
                             files={"file": (f"{inv}.pdf", b"%PDF-1.4 test", "application/pdf")})
            assert up.status_code == 201, up.text
    return rid


def submit(client, h, rid, who="partner.a", comment=None):
    return client.post(f"{API}/expense-reports/{rid}/submit", headers=h(who), json={"comment": comment} if comment else {})


def review(client, h, rid, stage, who, decision, comment="Reviewed with justification.", checklist=True):
    body = {"decision": decision, "comment": comment}
    if stage == "finance" and checklist:
        body["checklist"] = {"budget_available": True, "accounting_treatment_ok": True, "documents_ok": True}
    return client.post(f"{API}/expense-reports/{rid}/{stage}-review", headers=h(who), json=body)


OVER = [("pers", "10000", "INV-P"), ("supp", "2600", "INV-S")]  # supplies +30% / +600
OK = [("pers", "10300", "INV-P"), ("supp", "2000", "INV-S")]


# ------------------------------------------------------------------ authentication & authorization
def test_login_and_me(client, h):
    r = client.get(f"{API}/auth/me", headers=h("partner.a"))
    assert r.status_code == 200
    assert r.json()["roles"] == ["PARTNER"]


def test_login_wrong_password(client):
    r = client.post(f"{API}/auth/token", json={"email": "partner.a@test.local", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_endpoints_require_token(client):
    assert client.get(f"{API}/expense-reports").status_code == 401


def test_role_based_access_restrictions(client, h, world):
    assert client.post(f"{API}/partners", headers=h("auditor"), json={"code": "X1", "name": "Xyz"}).status_code == 403
    assert client.post(f"{API}/partners", headers=h("fin"), json={"code": "X1", "name": "Xyz"}).status_code == 403
    assert client.post(f"{API}/partners", headers=h("admin"), json={"code": "X1", "name": "Xyz"}).status_code == 201
    assert client.get(f"{API}/audit-logs", headers=h("auditor")).status_code == 200
    assert client.get(f"{API}/audit-logs", headers=h("partner.a")).status_code == 403
    assert client.post(f"{API}/expense-reports", headers=h("fin"), json={"project_id": world["project_id"], "fiscal_year": 2026, "period": 1}).status_code == 403


def test_partner_cannot_see_other_partners_report(client, h, world):
    rid = make_report(client, h, world, 1, OK)
    assert client.get(f"{API}/expense-reports/{rid}", headers=h("partner.b")).status_code == 404
    listing = client.get(f"{API}/expense-reports", headers=h("partner.b")).json()
    assert listing["total"] == 0


# ------------------------------------------------------------------ submission & controls
def test_auto_acceptance_within_tolerance(client, h, world):
    rid = make_report(client, h, world, 1, OK)
    r = submit(client, h, rid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "AUTO_ACCEPTED"
    assert [a["action"] for a in body["actions"]] == ["SUBMIT", "AUTO_ACCEPT"]
    assert body["exceptions"] == []


def test_variance_calculation_endpoint(client, h, world):
    rid = make_report(client, h, world, 2, OVER)
    v = client.get(f"{API}/expense-reports/{rid}/variance", headers=h("partner.a")).json()
    supp = next(row for row in v["rows"] if row["cost_category_id"] == world["supp"][0])
    assert supp["planned"] == "2000.00" and supp["actual"] == "2600.00"
    assert supp["variance"] == "600.00" and supp["variance_pct"] == "30.00"
    assert supp["ytd_planned"] == "4000.00" and supp["annual_planned"] == "24000.00"
    assert supp["within_tolerance"] is False
    assert v["auto_accept"] is False


def test_out_of_tolerance_routes_to_pm(client, h, world):
    rid = make_report(client, h, world, 1, OVER)
    body = submit(client, h, rid).json()
    assert body["status"] == "PENDING_PM_REVIEW"
    assert body["review_due_at"] is not None
    assert [e["exception_type"] for e in body["exceptions"]] == ["VARIANCE_OVER_TOLERANCE"]


def test_duplicate_invoice_detection(client, h, world):
    first = make_report(client, h, world, 1, OK)
    assert submit(client, h, first).json()["status"] == "AUTO_ACCEPTED"
    second = make_report(client, h, world, 2, [("pers", "10000", "INV-P"), ("supp", "2000", "INV-NEW")])
    body = submit(client, h, second).json()
    assert body["status"] == "PENDING_PM_REVIEW"
    assert "DUPLICATE_INVOICE" in [e["exception_type"] for e in body["exceptions"]]


def test_missing_plan_line_exception(client, h, world):
    rid = make_report(client, h, world, 1, OK + [("visb", "300", "INV-V")])
    body = submit(client, h, rid).json()
    assert body["status"] == "PENDING_PM_REVIEW"
    assert [e["exception_type"] for e in body["exceptions"]] == ["NO_PLAN_LINE"]


def test_missing_document_policy_block(client, h, world):
    r = client.put(f"{API}/config/settings/missing_document_policy", headers=h("admin"),
                   json={"value": "BLOCK", "change_reason": "Donor audit requirement"})
    assert r.status_code == 200
    rid = make_report(client, h, world, 1, OK, attach=False)
    r = submit(client, h, rid)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SUBMISSION_INVALID"


def test_missing_document_creates_exception_by_default(client, h, world):
    rid = make_report(client, h, world, 1, OK, attach=False)
    body = submit(client, h, rid).json()
    assert {e["exception_type"] for e in body["exceptions"]} == {"MISSING_DOCUMENT"}


def test_lines_locked_after_submission(client, h, world):
    rid = make_report(client, h, world, 1, OK)
    body = submit(client, h, rid).json()
    line_id = body["lines"][0]["id"]
    r = client.patch(f"{API}/expense-reports/{rid}/lines/{line_id}", headers=h("partner.a"), json={"amount": "1.00"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REPORT_LOCKED"


# ------------------------------------------------------------------ review workflow
def test_partner_cannot_approve_own_report(client, h, world):
    rid = make_report(client, h, world, 1, OVER)
    submit(client, h, rid)
    assert review(client, h, rid, "pm", "partner.a", "APPROVE").status_code == 403
    assert review(client, h, rid, "finance", "partner.a", "APPROVE").status_code == 403


def test_pm_review_workflow_and_assignment(client, h, world):
    rid = make_report(client, h, world, 1, OVER)
    submit(client, h, rid)
    # A PM not assigned to the project cannot even see the report (404, no id probing)
    assert review(client, h, rid, "pm", "pm.other", "APPROVE").status_code == 404
    r = review(client, h, rid, "pm", "pm", "APPROVE", comment="Extra supplies for flood response.")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PENDING_FINANCE_REVIEW"
    assert r.json()["exceptions"][0]["pm_justification"] == "Extra supplies for flood response."


def test_comment_is_mandatory(client, h, world):
    rid = make_report(client, h, world, 1, OVER)
    submit(client, h, rid)
    r = client.post(f"{API}/expense-reports/{rid}/pm-review", headers=h("pm"), json={"decision": "APPROVE", "comment": ""})
    assert r.status_code == 422


def test_final_approval_requires_pm_then_finance(client, h, world):
    rid = make_report(client, h, world, 1, OVER)
    submit(client, h, rid)
    # Finance cannot jump the PM step
    r = review(client, h, rid, "finance", "fin", "APPROVE")
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    # PM cannot give the final approval
    assert review(client, h, rid, "pm", "pm", "APPROVE").status_code == 200
    assert review(client, h, rid, "pm", "pm", "APPROVE").status_code == 409
    # Finance must confirm the checklist
    r = review(client, h, rid, "finance", "fin", "APPROVE", checklist=False)
    assert r.status_code == 422 and r.json()["error"]["code"] == "FINANCE_CHECKLIST_INCOMPLETE"
    r = review(client, h, rid, "finance", "fin", "APPROVE")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "APPROVED"
    assert body["pm_approved_by_id"] == world["users"]["pm"]
    assert body["finance_approved_by_id"] == world["users"]["fin"]
    assert all(e["status"] == "RESOLVED" for e in body["exceptions"])
    assert [a["action"] for a in body["actions"]] == ["SUBMIT", "ROUTE_TO_PM", "APPROVE", "APPROVE"]


def test_rejection_workflow(client, h, world):
    rid = make_report(client, h, world, 1, OVER)
    submit(client, h, rid)
    review(client, h, rid, "pm", "pm", "APPROVE")
    r = review(client, h, rid, "finance", "fin", "REJECT", comment="Cost not eligible under the agreement.")
    assert r.json()["status"] == "REJECTED"
    assert all(e["status"] == "REJECTED" for e in r.json()["exceptions"])
    # terminal: no further action possible
    assert review(client, h, rid, "finance", "fin2", "APPROVE").status_code == 409
    # a corrected report can be filed for the same period after rejection
    make_report(client, h, world, 1, [("pers", "10000", "INV-P2"), ("supp", "2000", "INV-S2")])


def test_return_for_clarification_and_resubmit(client, h, world):
    rid = make_report(client, h, world, 1, OVER)
    submit(client, h, rid)
    r = review(client, h, rid, "pm", "pm", "RETURN", comment="Please split the supplies invoice by activity.")
    assert r.json()["status"] == "RETURNED_FOR_CLARIFICATION"
    # partner edits the returned report, then must comment when resubmitting
    line = next(ln for ln in r.json()["lines"] if ln["invoice_reference"] == "INV-S")
    assert client.patch(f"{API}/expense-reports/{rid}/lines/{line['id']}", headers=h("partner.a"), json={"amount": "2050.00"}).status_code == 200
    assert submit(client, h, rid).status_code == 422  # comment required on RESUBMIT
    body = submit(client, h, rid, comment="Corrected: part of the invoice belonged to another project.").json()
    assert body["status"] == "AUTO_ACCEPTED"
    assert body["submission_count"] == 2
    assert {e["status"] for e in body["exceptions"]} == {"SUPERSEDED"}


def test_segregation_of_duties_on_role_assignment(client, h, world):
    r = client.post(f"{API}/users", headers=h("admin"), json={
        "email": "both@test.local", "full_name": "Both Roles", "password": "LongEnough#123",
        "roles": ["PROJECT_MANAGER", "FINANCE_OFFICER"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "SEGREGATION_OF_DUTIES"


# ------------------------------------------------------------------ audit trail
def test_audit_log_records_old_and_new_values(client, h, world):
    rid = make_report(client, h, world, 1, OK)
    detail = client.get(f"{API}/expense-reports/{rid}", headers=h("partner.a")).json()
    line_id = detail["lines"][0]["id"]
    client.patch(f"{API}/expense-reports/{rid}/lines/{line_id}", headers=h("partner.a"), json={"amount": "9999.00"})
    submit(client, h, rid)
    logs = client.get(f"{API}/audit-logs", headers=h("auditor"), params={"entity_type": "expense_lines", "entity_id": str(line_id), "size": 50}).json()["items"]
    update = next(l for l in logs if l["action"] == "UPDATE" and "amount" in (l["new_values"] or {}))
    assert update["old_values"]["amount"] == "10300.00"
    assert update["new_values"]["amount"] == "9999.00"
    assert update["actor_email"] == "partner.a@test.local"
    events = client.get(f"{API}/audit-logs", headers=h("auditor"), params={"entity_type": "expense_reports", "entity_id": str(rid), "size": 50}).json()["items"]
    actions = {e["action"] for e in events}
    assert {"CREATE", "SUBMIT"}.issubset(actions)


def test_config_change_is_audited(client, h, world):
    rules = client.get(f"{API}/config/tolerance-rules", headers=h("admin")).json()
    r = client.patch(f"{API}/config/tolerance-rules/{rules[0]['id']}", headers=h("admin"),
                     json={"max_variance_pct": "7.5", "change_reason": "Q3 policy review"})
    assert r.status_code == 200
    logs = client.get(f"{API}/audit-logs", headers=h("auditor"), params={"entity_type": "tolerance_rules"}).json()["items"]
    assert any(l["action"] == "CONFIG_CHANGE" and l["comment"] == "Q3 policy review" for l in logs)


# ------------------------------------------------------------------ dashboard & exports
def test_dashboard_and_exports(client, h, world):
    rid = make_report(client, h, world, 1, OK)
    submit(client, h, rid)
    s = client.get(f"{API}/dashboard/summary", params={"fiscal_year": 2026}, headers=h("fin")).json()
    assert s["status_counts"]["AUTO_ACCEPTED"] == 1
    assert s["planned_total"] == "288000.00"
    pva = client.get(f"{API}/dashboard/plan-vs-actual", params={"fiscal_year": 2026}, headers=h("fin")).json()
    assert pva[0]["actual"] == "12300.00"
    csv = client.get(f"{API}/reports/monthly-variance", params={"fiscal_year": 2026, "period": 1, "format": "csv"}, headers=h("fin"))
    assert csv.status_code == 200 and "planned" in csv.text
    xlsx = client.get(f"{API}/reports/expense-reports/export", params={"fiscal_year": 2026, "format": "xlsx"}, headers=h("auditor"))
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"


def test_closed_period_refuses_submission(client, h, world):
    rid = make_report(client, h, world, 3, OK)
    periods = client.get(f"{API}/config/reporting-periods", params={"fiscal_year": 2026}, headers=h("admin")).json()
    march = next(p for p in periods if p["period"] == 3)
    r = client.patch(f"{API}/config/reporting-periods/{march['id']}", headers=h("admin"), json={**march, "status": "CLOSED"})
    assert r.status_code == 200
    r = submit(client, h, rid)
    assert r.status_code == 422
    assert any("not open" in e for e in r.json()["error"]["details"]["errors"])
