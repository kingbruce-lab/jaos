from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select

from app.models import AuditLog, EducationInstallment, EducationPayment
from test_education_enrollment import make_cohort, student_payload
from test_education_system import setup


def create_student(client, path, **changes):
    response = client.post(path + "/students", json=student_payload(received="0", fees=[
        {"category": "学费", "detail": "课程学费", "receivable": "10000", "cost": "0"},
        {"category": "住宿费", "detail": "两人间", "receivable": "0", "cost": "1800"},
        {"category": "饭费", "detail": "餐费套餐", "receivable": "0", "cost": "1200"},
    ], **changes))
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_ledger_search_installments_receipts_refunds_and_scope(setup):
    client, db, users, actor = setup
    path = make_cohort(client)
    student_id = create_student(client, path, name="张三")
    student_path = path + "/students/" + student_id
    installment = {"request_id": str(uuid4()), "label": "定金", "due_on": "2026-10-01", "amount": "3000", "note": "报名确认", "active": True}
    saved_plan = client.post(student_path + "/installments", json=installment)
    assert saved_plan.status_code == 200, saved_plan.text
    assert client.post(student_path + "/installments", json=installment).json() == saved_plan.json()
    receipt = {"request_id": str(uuid4()), "direction": "receipt", "amount": "3000", "occurred_on": "2026-09-20",
        "method": "银行转账", "account": "公司基本户", "note": "定金", "installment_id": saved_plan.json()["id"]}
    saved_payment = client.post(student_path + "/payments", json=receipt)
    assert saved_payment.status_code == 200, saved_payment.text
    assert client.post(student_path + "/payments", json=receipt).json() == saved_payment.json()
    detail = client.get(student_path + "/payment-ledger").json()
    assert detail["summary"] == {"receivable": "10000.00", "net_received": "3000.00", "arrears": "7000.00",
        "overpayment": "0.00", "plan_total": "3000.00", "plan_difference": "7000.00"}
    assert detail["installments"][0]["paid"] == "3000.00"
    refund = {**receipt, "request_id": str(uuid4()), "direction": "refund", "amount": "500", "note": "退还部分定金", "installment_id": None}
    assert client.post(student_path + "/payments", json=refund).status_code == 200
    assert client.get(student_path).json()["received"] == "2500.00"
    assert client.post(student_path + "/payments", json={**refund, "request_id": str(uuid4()), "amount": "3000"}).status_code == 422
    structured_cost = client.post(path + "/cost-documents", json={
        "request_id": str(uuid4()), "occurred_on": "2026-10-01", "ended_on": "2026-10-02",
        "category": "饭费", "detail": "餐费套餐", "unit_price": "100.00",
    })
    assert structured_cost.status_code == 200, structured_cost.text
    cash_expense = client.post(path + "/entries", json={
        "request_id": str(uuid4()), "direction": "expense", "amount": "50.00",
        "occurred_on": "2026-10-03", "ended_on": "2026-10-03", "purpose": "临时交通费",
        "category": "活动经费", "detail": "交通费",
    })
    assert cash_expense.status_code == 200, cash_expense.text
    result = client.get("/v1/pm/education/ledger?keyword=张三&payment_status=arrears").json()
    assert result["summary"]["receivable"] == "10000.00"
    assert result["summary"]["student_cost"] == "3000.00"
    assert result["summary"]["recorded_cost"] == "200.00"
    assert result["summary"]["cash_expense"] == "50.00"
    assert result["summary"]["cost"] == "3250.00"
    assert result["items"][0]["cohort_name"] == "十月托管教培"
    actor[0] = users["other"]
    assert client.get("/v1/pm/education/ledger?keyword=张三").json()["summary"]["student_count"] == 0
    actor[0] = users["finance"]
    assert client.get(student_path + "/payment-ledger").status_code == 200
    assert client.post(student_path + "/payments", json={**receipt, "request_id": str(uuid4())}).status_code == 403
    assert db.scalar(select(func.count(EducationPayment.id))) == 2
    assert db.scalar(select(func.count(EducationInstallment.id))) == 1
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "education_payment_created")) == 2


def test_payment_correction_replaces_total_and_inactive_plan_is_retained(setup):
    client, db, *_ = setup
    path = make_cohort(client)
    student_id = create_student(client, path)
    student_path = path + "/students/" + student_id
    payment = {"request_id": str(uuid4()), "direction": "receipt", "amount": "1000", "occurred_on": "2026-09-20",
        "method": "微信", "account": "", "note": "首款", "installment_id": None}
    payment_id = client.post(student_path + "/payments", json=payment).json()["id"]
    update = {key: value for key, value in payment.items() if key != "request_id"}
    update.update(version=1, amount="1500")
    assert client.patch(student_path + "/payments/" + payment_id, json=update).status_code == 200
    assert client.patch(student_path + "/payments/" + payment_id, json=update).status_code == 409
    assert client.get(student_path).json()["received"] == "1500.00"
    plan = {"request_id": str(uuid4()), "label": "尾款", "due_on": "2026-10-15", "amount": "8500", "note": "", "active": True}
    plan_id = client.post(student_path + "/installments", json=plan).json()["id"]
    patch = {key: value for key, value in plan.items() if key != "request_id"}
    patch.update(version=1, active=False)
    assert client.patch(student_path + "/installments/" + plan_id, json=patch).status_code == 200
    ledger = client.get(student_path + "/payment-ledger").json()
    assert ledger["installments"][0]["active"] is False and ledger["summary"]["plan_total"] == "0.00"
