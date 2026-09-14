from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import bootstrap_admin, current_user
from app.database import get_db
from app.education_system import month_end
from app.main import app
from app.models import AuditLog, Base, BusinessEntity, EducationCashEntry, EducationCohort, User
from app.retrieval import _authorized_levels, is_authorized


@pytest.fixture
def setup():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    users = {key: User(username=key, display_name=key, password_hash="x", role=role,
                      organization_role=org, confidentiality_ceiling=level) for key, role, org, level in [
        ("teacher", "employee", "education", "L1"), ("other", "employee", "education", "L1"),
        ("founder", "founder", "management", "L5"), ("finance", "employee", "finance", "L4"),
        ("business", "employee", "business", "L3"), ("admin", "knowledge_admin", "administrative", "L4"),
    ]}
    db.add_all(users.values()); db.flush()
    db.add(BusinessEntity(name="星曜电竞", short_name="星曜电竞", created_by_user_id=users["founder"].id))
    db.commit()
    actor = [users["teacher"]]
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: actor[0]
    yield TestClient(app), db, users, actor
    app.dependency_overrides.clear()
    db.close(); engine.dispose()


def cohort_payload(**overrides):
    return {"request_id": str(uuid4()), "name": "十月托管教培", "start_date": "2026-10-01",
            "student_count": 12, "unit_price": "3500.50", "notes": "一期", **overrides}


def entry_payload(**overrides):
    return {"request_id": str(uuid4()), "direction": "income", "amount": "10000.25",
            "occurred_on": "2026-10-01", "purpose": "学费首款", **overrides}


def test_education_role_is_forced_to_l1_on_create_and_every_policy_update(setup):
    client, db, users, actor = setup
    actor[0] = users["founder"]
    result = client.post("/v1/admin/users", json={"username": "newteacher", "display_name": "教培员工",
        "password": "test-password-2026", "role": "education", "confidentiality_ceiling": "L5"})
    assert result.status_code == 200
    assert result.json()["organization_role"] == "education"
    assert result.json()["role"] == "employee"
    assert result.json()["confidentiality_ceiling"] == "L1"
    user_id = result.json()["id"]
    assert client.patch(f"/v1/admin/users/{user_id}", json={"confidentiality_ceiling": "L4"}).json()["confidentiality_ceiling"] == "L1"
    changed = client.patch(f"/v1/admin/users/{users['business'].id}", json={"role": "education"})
    assert changed.json()["confidentiality_ceiling"] == "L1"
    bootstrap_admin(db)
    assert db.get(User, user_id).organization_role == "education"
    assert db.get(User, user_id).confidentiality_ceiling == "L1"
    actor[0] = db.get(User, user_id)
    assert client.get("/v1/pm/education/cohorts").status_code == 200
    assert client.get("/v1/pm/projects").status_code == 403
    assert client.get("/v1/finance/entities").status_code == 403
    assert client.get("/v1/admin/users").status_code == 403
    assert client.get("/v1/contracts/categories").status_code == 403
    assert _authorized_levels(actor[0]) == ("L1",)
    for level in ("L2", "L3", "L4", "L5"):
        assert not is_authorized(actor[0], SimpleNamespace(confidentiality=level), SimpleNamespace(confidentiality="L1"))
    assert is_authorized(actor[0], SimpleNamespace(confidentiality="L1"), SimpleNamespace(confidentiality="L1"))


def test_monthly_cohorts_accumulate_and_corrections_replace_not_duplicate(setup):
    client, db, users, actor = setup
    first = cohort_payload()
    response = client.post("/v1/pm/education/cohorts", json=first)
    assert response.status_code == 200
    path = f"/v1/pm/education/cohorts/{response.json()['id']}"
    assert client.post("/v1/pm/education/cohorts", json=first).json() == response.json()
    assert client.post("/v1/pm/education/cohorts", json={**first, "student_count": 99}).status_code == 409
    detail = client.get(path).json()
    assert detail["end_date"] == "2026-10-29"
    assert detail["expected_income"] == "42006.00"
    assert detail["income"] == "0.00"
    income = entry_payload()
    saved = client.post(path + "/entries", json=income)
    assert saved.status_code == 200
    assert client.get(path).json()["entries"][0]["ended_on"] == "2026-10-01"
    assert client.post(path + "/entries", json=income).json() == saved.json()
    assert client.post(path + "/entries", json={**income, "amount": "999"}).status_code == 409
    assert client.post(path + "/entries", json=entry_payload(direction="expense", amount="1234.56", purpose="住宿费")).status_code == 200
    second = client.post("/v1/pm/education/cohorts", json=cohort_payload(name="十一月班", start_date="2026-11-01", student_count=8, unit_price="4000"))
    assert second.status_code == 200
    assert client.post(f"/v1/pm/education/cohorts/{second.json()['id']}/entries", json=entry_payload(amount="32000")).status_code == 200
    summary = client.get("/v1/pm/education/cohorts?limit=1").json()
    assert summary["has_more"]
    assert len(summary["items"]) == 1
    assert summary["summary"] == {"cohort_count": 2, "student_count": 20, "expected_income": "74006.00",
        "income": "42000.25", "student_cost": "0.00", "cost": "0.00", "cash_expense": "1234.56", "operating_expense": "1234.56",
        "expense": "1234.56", "net": "40765.69"}
    assert not client.get("/v1/pm/education/cohorts?limit=1&offset=1").json()["has_more"]
    update = {key: value for key, value in first.items() if key != "request_id"}
    update.update(student_count=13, version=1)
    assert client.patch(path, json=update).status_code == 200
    assert client.patch(path, json=update).status_code == 409
    corrected = {key: value for key, value in income.items() if key != "request_id"}
    corrected.update(amount="11000.25", version=1)
    assert client.patch(path + "/entries/" + saved.json()["id"], json=corrected).status_code == 200
    assert client.patch(path + "/entries/" + saved.json()["id"], json=corrected).status_code == 409
    final = client.get(path).json()
    assert final["student_count"] == 13
    assert final["income"] == "11000.25"
    assert final["net"] == "9765.69"
    assert len(final["entries"]) == 2
    assert db.scalar(select(func.count(EducationCashEntry.id))) == 3
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "education_entry_updated"))
    assert '10000.25' in audit.details_json and '11000.25' in audit.details_json


def test_education_employee_isolation_and_finance_read_only(setup):
    client, db, users, actor = setup
    result = client.post("/v1/pm/education/cohorts", json=cohort_payload())
    path = f"/v1/pm/education/cohorts/{result.json()['id']}"
    entry = client.post(path + "/entries", json=entry_payload()).json()
    actor[0] = users["other"]
    assert client.get("/v1/pm/education/cohorts").json()["summary"]["cohort_count"] == 0
    for route in (path, path + "/entries"):
        assert client.get(route).status_code == 404
    assert client.post(path + "/entries", json=entry_payload()).status_code == 404
    update = {key: value for key, value in cohort_payload().items() if key != "request_id"}
    update["version"] = 1
    assert client.patch(path, json=update).status_code == 404
    actor[0] = users["finance"]
    assert client.get(path).status_code == 200
    assert client.get("/v1/pm/education/cohorts").json()["can_edit"] is False
    assert client.post("/v1/pm/education/cohorts", json=cohort_payload()).status_code == 403
    assert client.patch(path, json=update).status_code == 403
    assert client.post(path + "/entries", json=entry_payload()).status_code == 403
    for key in ("business", "admin"):
        actor[0] = users[key]
        assert client.get("/v1/pm/education/cohorts").status_code == 403
        assert client.get(path).status_code == 403
    actor[0] = users["founder"]
    assert client.get("/v1/pm/education/cohorts").json()["summary"]["cohort_count"] == 1
    assert client.patch(path, json=update).status_code == 200
    actor[0] = users["teacher"]
    actor[0].active = False
    assert client.get(path).status_code == 403


@pytest.mark.parametrize("overrides", [{"student_count": -1}, {"student_count": 1.5}, {"unit_price": "-1"},
    {"unit_price": "NaN"}, {"unit_price": "10.001"}, {"name": "  "}, {"entity_id": "injected"}, {"owner_user_id": "other"}])
def test_invalid_cohorts_rejected(setup, overrides):
    client, db, _, _ = setup
    assert client.post("/v1/pm/education/cohorts", json=cohort_payload(**overrides)).status_code == 422
    assert db.scalar(select(func.count(EducationCohort.id))) == 0


@pytest.mark.parametrize("overrides", [{"amount": "0"}, {"amount": "-10"}, {"amount": "Infinity"}, {"amount": "1.234"}, {"direction": "other"}, {"purpose": " "}])
def test_invalid_entries_rejected(setup, overrides):
    client, db, _, _ = setup
    cohort_id = client.post("/v1/pm/education/cohorts", json=cohort_payload()).json()["id"]
    assert client.post(f"/v1/pm/education/cohorts/{cohort_id}/entries", json=entry_payload(**overrides)).status_code == 422
    assert db.scalar(select(func.count(EducationCashEntry.id))) == 0


def test_entry_period_has_end_date_and_rejects_reverse_range(setup):
    client, _, _, _ = setup
    cohort_id = client.post("/v1/pm/education/cohorts", json=cohort_payload()).json()["id"]
    path = f"/v1/pm/education/cohorts/{cohort_id}/entries"
    saved = client.post(path, json=entry_payload(occurred_on="2026-10-02", ended_on="2026-10-08"))
    assert saved.status_code == 200, saved.text
    detail = client.get(f"/v1/pm/education/cohorts/{cohort_id}").json()
    assert detail["entries"][0]["ended_on"] == "2026-10-08"
    rejected = client.post(path, json=entry_payload(occurred_on="2026-10-08", ended_on="2026-10-02"))
    assert rejected.status_code == 422


def test_month_duration_boundaries():
    assert month_end(date(2026, 12, 1)) == date(2026, 12, 29)
    assert month_end(date(2028, 2, 1)) == date(2028, 2, 29)
    assert month_end(date(2026, 1, 31)) == date(2026, 2, 28)
    assert month_end(date(2026, 10, 1), "3_months") == date(2026, 12, 26)
