"""Cross-cohort education ledger, installment plans and auditable cash detail."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from .auth import current_user
from .database import get_db
from .education_system import _audit, _cohort, _commit, _money, _require_access, _scope
from .models import (
    EducationCohort, EducationCostAllocation, EducationCostDocument,
    EducationInstallment, EducationPayment, EducationStudent, User,
)

router = APIRouter(prefix="/v1/pm/education", tags=["education-ledger"])
PAYMENT_METHODS = ("现金", "微信", "支付宝", "银行转账", "其他")


class InstallmentFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=80)
    due_on: date
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    note: str = Field(default="", max_length=1000)
    active: bool = True

    @field_validator("due_on")
    @classmethod
    def valid_date(cls, value: date) -> date:
        if not 2000 <= value.year <= 2100:
            raise ValueError("日期须在 2000 至 2100 年之间")
        return value


class InstallmentCreate(InstallmentFields):
    request_id: UUID


class InstallmentUpdate(InstallmentFields):
    version: int = Field(ge=1)


class PaymentFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    direction: Literal["receipt", "refund"]
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    occurred_on: date
    method: Literal["现金", "微信", "支付宝", "银行转账", "其他"]
    account: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=1000)
    installment_id: UUID | None = None

    @field_validator("occurred_on")
    @classmethod
    def valid_date(cls, value: date) -> date:
        if not 2000 <= value.year <= 2100:
            raise ValueError("日期须在 2000 至 2100 年之间")
        return value


class PaymentCreate(PaymentFields):
    request_id: UUID


class PaymentUpdate(PaymentFields):
    version: int = Field(ge=1)


def _student(db: Session, user: User, cohort_id: str, student_id: str, *, write: bool = False) -> EducationStudent:
    _cohort(db, user, cohort_id, write=write)
    row = db.scalar(select(EducationStudent).where(
        EducationStudent.id == student_id, EducationStudent.cohort_id == cohort_id,
    ).with_for_update() if write else select(EducationStudent).where(
        EducationStudent.id == student_id, EducationStudent.cohort_id == cohort_id,
    ))
    if row is None:
        raise HTTPException(404, "学员记录不存在或无权访问")
    return row


def _installment_data(row: EducationInstallment, paid: Decimal = Decimal(0)) -> dict:
    return {
        "id": row.id, "student_id": row.student_id, "label": row.label,
        "due_on": row.due_on.isoformat(), "amount": _money(row.amount),
        "paid": _money(paid), "remaining": _money(max(row.amount - paid, Decimal(0))),
        "note": row.note, "active": row.active, "version": row.version,
    }


def _payment_data(row: EducationPayment, creator_name: str = "") -> dict:
    return {
        "id": row.id, "student_id": row.student_id, "direction": row.direction,
        "amount": _money(row.amount), "occurred_on": row.occurred_on.isoformat(),
        "method": row.method, "account": row.account, "note": row.note,
        "installment_id": row.installment_id, "creator_name": creator_name,
        "created_by_user_id": row.created_by_user_id, "version": row.version,
    }


def _signed(direction: str, amount: Decimal) -> Decimal:
    return amount if direction == "receipt" else -amount


def _assert_installment(db: Session, student: EducationStudent, installment_id: UUID | None) -> str | None:
    if not installment_id:
        return None
    value = str(installment_id)
    row = db.get(EducationInstallment, value)
    if row is None or row.student_id != student.id or row.cohort_id != student.cohort_id or not row.active:
        raise HTTPException(422, "请选择本学员有效的分期计划")
    return value


@router.get("/ledger")
def ledger_overview(
    keyword: str = Query("", max_length=120), cohort_id: str | None = None,
    payment_status: Literal["all", "arrears", "paid", "overpaid"] = "all",
    offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user), db: Session = Depends(get_db),
) -> dict:
    _require_access(user)
    scoped = _scope(user).subquery()
    where = [EducationStudent.cohort_id.in_(select(scoped.c.id))]
    if cohort_id:
        where.append(EducationStudent.cohort_id == cohort_id)
    cleaned = keyword.strip()
    if cleaned:
        escaped = cleaned.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append(or_(EducationStudent.name.ilike(f"%{escaped}%", escape="\\"),
                         EducationCohort.name.ilike(f"%{escaped}%", escape="\\"),
                         EducationStudent.game.ilike(f"%{escaped}%", escape="\\")))
    if payment_status == "arrears":
        where.append(EducationStudent.receivable > EducationStudent.received)
    elif payment_status == "paid":
        where.append(EducationStudent.receivable == EducationStudent.received)
    elif payment_status == "overpaid":
        where.append(EducationStudent.received > EducationStudent.receivable)
    base = select(EducationStudent, EducationCohort.name).join(
        EducationCohort, EducationCohort.id == EducationStudent.cohort_id,
    ).where(*where)
    rows = db.execute(base.order_by(EducationStudent.registration_date.desc(), EducationStudent.id)
                      .offset(offset).limit(limit)).all()
    row_ids = [row.id for row, _ in rows]
    allocated_by_student = dict(db.execute(select(
        EducationCostAllocation.student_id, func.coalesce(func.sum(EducationCostAllocation.amount), 0),
    ).join(EducationCostDocument, EducationCostDocument.id == EducationCostAllocation.cost_document_id)
      .where(EducationCostAllocation.student_id.in_(row_ids), EducationCostDocument.active.is_(True))
      .group_by(EducationCostAllocation.student_id)).all()) if row_ids else {}
    totals = db.execute(select(
        func.count(EducationStudent.id),
        func.coalesce(func.sum(EducationStudent.receivable), 0),
        func.coalesce(func.sum(EducationStudent.received), 0),
        func.coalesce(func.sum(EducationStudent.cost), 0),
        func.coalesce(func.sum(case((EducationStudent.receivable > EducationStudent.received,
            EducationStudent.receivable - EducationStudent.received), else_=0)), 0),
        func.coalesce(func.sum(case((EducationStudent.received > EducationStudent.receivable,
            EducationStudent.received - EducationStudent.receivable), else_=0)), 0),
    ).select_from(EducationStudent).join(EducationCohort, EducationCohort.id == EducationStudent.cohort_id)
      .where(*where)).one()
    allocated_total = db.scalar(select(func.coalesce(func.sum(EducationCostAllocation.amount), 0))
        .select_from(EducationCostAllocation)
        .join(EducationCostDocument, EducationCostDocument.id == EducationCostAllocation.cost_document_id)
        .join(EducationStudent, EducationStudent.id == EducationCostAllocation.student_id)
        .join(EducationCohort, EducationCohort.id == EducationStudent.cohort_id)
        .where(EducationCostDocument.active.is_(True), *where)) or Decimal(0)
    return {
        "items": [{
            "id": row.id, "cohort_id": row.cohort_id, "cohort_name": cohort_name,
            "name": row.name, "registration_date": row.registration_date.isoformat(),
            "game": row.game, "course_period": row.course_period,
            "study_start": row.study_start.isoformat(), "study_end": row.study_end.isoformat(),
            "receivable": _money(row.receivable), "received": _money(row.received),
            "arrears": _money(max(row.receivable - row.received, Decimal(0))),
            "overpayment": _money(max(row.received - row.receivable, Decimal(0))),
            "cost": _money(row.cost + allocated_by_student.get(row.id, Decimal(0))),
            "allocated_cost": _money(allocated_by_student.get(row.id, Decimal(0))),
        } for row, cohort_name in rows],
        "summary": {"student_count": totals[0], "receivable": _money(totals[1]),
                    "received": _money(totals[2]), "cost": _money(totals[3] + allocated_total),
                    "arrears": _money(totals[4]), "overpayment": _money(totals[5])},
        "has_more": offset + len(rows) < totals[0],
        "scope": "mine" if user.organization_role == "education" else "all",
    }


@router.get("/cohorts/{cohort_id}/students/{student_id}/payment-ledger")
def payment_ledger(cohort_id: str, student_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    student = _student(db, user, cohort_id, student_id)
    paid_by_installment = dict(db.execute(select(
        EducationPayment.installment_id,
        func.coalesce(func.sum(case((EducationPayment.direction == "receipt", EducationPayment.amount), else_=-EducationPayment.amount)), 0),
    ).where(EducationPayment.student_id == student.id, EducationPayment.installment_id.is_not(None))
      .group_by(EducationPayment.installment_id)).all())
    plans = db.scalars(select(EducationInstallment).where(EducationInstallment.student_id == student.id)
                       .order_by(EducationInstallment.due_on, EducationInstallment.created_at)).all()
    payments = db.execute(select(EducationPayment, User.display_name).join(
        User, User.id == EducationPayment.created_by_user_id,
    ).where(EducationPayment.student_id == student.id)
      .order_by(EducationPayment.occurred_on.desc(), EducationPayment.created_at.desc())).all()
    plan_total = sum((row.amount for row in plans if row.active), Decimal(0))
    return {
        "installments": [_installment_data(row, Decimal(paid_by_installment.get(row.id, 0))) for row in plans],
        "payments": [_payment_data(row, name) for row, name in payments],
        "methods": PAYMENT_METHODS,
        "summary": {"receivable": _money(student.receivable), "net_received": _money(student.received),
                    "arrears": _money(max(student.receivable - student.received, Decimal(0))),
                    "overpayment": _money(max(student.received - student.receivable, Decimal(0))),
                    "plan_total": _money(plan_total), "plan_difference": _money(student.receivable - plan_total)},
    }


@router.post("/cohorts/{cohort_id}/students/{student_id}/installments")
def create_installment(cohort_id: str, student_id: str, payload: InstallmentCreate,
                       user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    student = _student(db, user, cohort_id, student_id, write=True)
    existing = db.get(EducationInstallment, str(payload.request_id))
    values = payload.model_dump(exclude={"request_id"})
    if existing:
        if existing.student_id != student.id or any(getattr(existing, key) != value for key, value in values.items()):
            raise HTTPException(409, "提交标识冲突，请刷新后重试")
        return {"id": existing.id}
    row = EducationInstallment(id=str(payload.request_id), student_id=student.id, cohort_id=cohort_id,
        created_by_user_id=user.id, version=1, **values)
    db.add(row)
    _audit(db, user, "education_installment_created", None, {"id": row.id, "student_id": student.id,
        "amount": _money(row.amount), "due_on": row.due_on.isoformat(), "label": row.label})
    _commit(db)
    return {"id": row.id}


@router.patch("/cohorts/{cohort_id}/students/{student_id}/installments/{installment_id}")
def update_installment(cohort_id: str, student_id: str, installment_id: str, payload: InstallmentUpdate,
                       user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    student = _student(db, user, cohort_id, student_id, write=True)
    row = db.scalar(select(EducationInstallment).where(EducationInstallment.id == installment_id,
        EducationInstallment.student_id == student.id).with_for_update())
    if row is None:
        raise HTTPException(404, "分期计划不存在")
    if row.version != payload.version:
        raise HTTPException(409, "分期计划已更新，请刷新后再试")
    before = _installment_data(row)
    for key, value in payload.model_dump(exclude={"version"}).items():
        setattr(row, key, value)
    row.version += 1
    _audit(db, user, "education_installment_updated", before, _installment_data(row))
    _commit(db)
    return {"id": row.id}


@router.post("/cohorts/{cohort_id}/students/{student_id}/payments")
def create_payment(cohort_id: str, student_id: str, payload: PaymentCreate,
                   user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    student = _student(db, user, cohort_id, student_id, write=True)
    values = payload.model_dump(exclude={"request_id", "installment_id"})
    values["installment_id"] = _assert_installment(db, student, payload.installment_id)
    existing = db.get(EducationPayment, str(payload.request_id))
    if existing:
        if existing.student_id != student.id or any(getattr(existing, key) != value for key, value in values.items()):
            raise HTTPException(409, "提交标识冲突，请刷新后重试")
        return {"id": existing.id}
    delta = _signed(payload.direction, payload.amount)
    if student.received + delta < 0:
        raise HTTPException(422, "退款不能超过当前净实收金额")
    row = EducationPayment(id=str(payload.request_id), student_id=student.id, cohort_id=cohort_id,
        created_by_user_id=user.id, version=1, **values)
    student.received += delta
    student.version += 1
    db.add(row)
    _audit(db, user, "education_payment_created", None, {"id": row.id, "student_id": student.id,
        "direction": row.direction, "amount": _money(row.amount), "occurred_on": row.occurred_on.isoformat(),
        "net_received": _money(student.received)})
    _commit(db)
    return {"id": row.id}


@router.patch("/cohorts/{cohort_id}/students/{student_id}/payments/{payment_id}")
def update_payment(cohort_id: str, student_id: str, payment_id: str, payload: PaymentUpdate,
                   user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    student = _student(db, user, cohort_id, student_id, write=True)
    row = db.scalar(select(EducationPayment).where(EducationPayment.id == payment_id,
        EducationPayment.student_id == student.id).with_for_update())
    if row is None:
        raise HTTPException(404, "收退款记录不存在")
    if row.version != payload.version:
        raise HTTPException(409, "收退款记录已更新，请刷新后再试")
    values = payload.model_dump(exclude={"version", "installment_id"})
    values["installment_id"] = _assert_installment(db, student, payload.installment_id)
    before = _payment_data(row)
    new_total = student.received - _signed(row.direction, row.amount) + _signed(payload.direction, payload.amount)
    if new_total < 0:
        raise HTTPException(422, "退款不能超过当前净实收金额")
    for key, value in values.items():
        setattr(row, key, value)
    row.version += 1
    student.received = new_total
    student.version += 1
    _audit(db, user, "education_payment_updated", before, {**_payment_data(row), "net_received": _money(new_total)})
    _commit(db)
    return {"id": row.id}
