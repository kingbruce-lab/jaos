"""Isolated monthly education operations; never grants general PM/KB access."""
from __future__ import annotations

import json
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import case, func, literal, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_user, verify_password
from .project_system import _reviewer_slot, _require_project_founder, _check_delete_rate_limit, project_delete_rate_limiter
from .database import get_db
from .models import (
    AuditLog, BusinessEntity, EducationCashEntry, EducationCohort,
    EducationCostAllocation, EducationCostDocument, EducationStudent, EducationStaff, User,
)
from .education_catalog import PERIODS, FEE_DETAILS

router = APIRouter(prefix="/v1/pm/education", tags=["education-management"])


class CohortFields(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    start_date: date
    course_period: Literal["8_days", "1_month", "3_months"] = "1_month"
    student_count: int = Field(ge=0, le=100000, strict=True)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    notes: str = Field(default="", max_length=2000)

    @field_validator("start_date")
    @classmethod
    def valid_date(cls, value: date) -> date:
        if not 2000 <= value.year <= 2100:
            raise ValueError("开班日期须在 2000 至 2100 年之间")
        return value


class CohortCreate(CohortFields):
    request_id: UUID


class CohortUpdate(CohortFields):
    version: int = Field(ge=1)


class CohortDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deletion_password: str = Field(min_length=1, max_length=200)
    confirm_name: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=2, max_length=1000)
    version: int = Field(ge=1)


class EntryFields(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    direction: Literal["income", "expense"]
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    occurred_on: date
    ended_on: date | None = None
    purpose: str = Field(min_length=1, max_length=500)
    category: str = "其他"
    detail: str = "其他"
    staff_id: UUID | None = None

    @model_validator(mode="after")
    def valid_period(self):
        if self.ended_on and self.ended_on < self.occurred_on:
            raise ValueError("结束日期不能早于发生日期")
        return self


class EntryCreate(EntryFields):
    request_id: UUID


class EntryUpdate(EntryFields):
    version: int = Field(ge=1)


def _management(user: User) -> bool:
    return user.organization_role == "management" and user.confidentiality_ceiling == "L5"


def _require_access(user: User, *, write: bool = False) -> None:
    allowed = user.organization_role == "education" or _management(user)
    if not write:
        allowed = allowed or (user.organization_role == "finance" and user.confidentiality_ceiling in {"L4", "L5"})
    if not user.active or not allowed:
        raise HTTPException(403, "无权操作教培项目模块")


def _scope(user: User):
    statement = select(EducationCohort).where(EducationCohort.deleted_at.is_(None))
    if user.organization_role == "education":
        statement = statement.where(EducationCohort.owner_user_id == user.id)
    return statement


def _cohort(db: Session, user: User, cohort_id: str, *, write: bool = False) -> EducationCohort:
    _require_access(user, write=write)
    statement = _scope(user).where(EducationCohort.id == cohort_id)
    if write:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None:
        raise HTTPException(404, "教培班期不存在或无权访问")
    return row


def month_end(start: date, period: str = "1_month") -> date:
    if period == "8_days":
        return start + timedelta(days=7)
    # Confirmed education policy: one month is 29 inclusive calendar days and
    # three months are 87 inclusive calendar days. Teaching/self-practice days
    # are scheduled separately and do not change this contractual duration.
    return start + timedelta(days=86 if period == "3_months" else 28)


def _money(value) -> str:
    return format(Decimal(value or 0).quantize(Decimal("0.01")), "f")


def _audit(db: Session, user: User, action: str, before: dict | None, after: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=action, details_json=json.dumps(
        {"before": before, "after": after}, ensure_ascii=False, default=str,
    )))


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "记录已提交，请刷新后确认，勿重复添加") from None


def _cohort_data(row: EducationCohort) -> dict:
    return {"id": row.id, "entity_id": row.entity_id, "owner_user_id": row.owner_user_id,
            "name": row.name, "start_date": row.start_date.isoformat(),
            "end_date": month_end(row.start_date, row.course_period).isoformat(),
            "course_period": row.course_period,
            "student_count": row.student_count, "unit_price": _money(row.unit_price),
            "expected_income": _money(row.unit_price * row.student_count), "notes": row.notes,
            "version": row.version}


def _entry_data(row: EducationCashEntry) -> dict:
    return {"id": row.id, "cohort_id": row.cohort_id, "direction": row.direction,
            "amount": _money(row.amount), "occurred_on": row.occurred_on.isoformat(),
            "ended_on": (row.ended_on or row.occurred_on).isoformat(),
            "purpose": row.purpose, "category": row.category, "detail": row.detail, "staff_id": row.staff_id,
            "version": row.version, "created_by_user_id": row.created_by_user_id}


def _entry_fields(db: Session, cohort_id: str, payload: EntryFields, previous=None) -> dict:
    if payload.category not in FEE_DETAILS or payload.detail not in FEE_DETAILS[payload.category]:
        raise HTTPException(422, "请选择有效的费用分类和明细")
    staff_id = str(payload.staff_id) if payload.staff_id else None
    if payload.category == "人员成本":
        staff = db.get(EducationStaff, staff_id) if staff_id else None
        if staff is None or staff.cohort_id != cohort_id or staff.role != payload.detail:
            raise HTTPException(422, "请选择本班期对应类型的教师或助教")
        if not staff.active and (previous is None or previous.staff_id != staff_id):
            raise HTTPException(422, "该人员已移除，请选择在册人员")
    elif staff_id:
        raise HTTPException(422, "仅人员成本可关联教师或助教")
    values = payload.model_dump(exclude={"request_id", "version", "staff_id"})
    values["ended_on"] = payload.ended_on or payload.occurred_on
    return {**values, "staff_id": staff_id}


def _totals(db: Session, cohort_ids):
    sources = union_all(select(
        EducationCashEntry.cohort_id.label("cohort_id"),
        case((EducationCashEntry.direction == "income", EducationCashEntry.amount), else_=0).label("income"),
        case((EducationCashEntry.direction == "expense", EducationCashEntry.amount), else_=0).label("expense"),
    ).where(EducationCashEntry.cohort_id.in_(cohort_ids)), select(
        EducationStudent.cohort_id, EducationStudent.received, EducationStudent.cost,
    ).where(EducationStudent.cohort_id.in_(cohort_ids)), select(
        EducationCostAllocation.cohort_id,
        literal(Decimal("0")).label("income"),
        EducationCostAllocation.amount.label("expense"),
    ).join(EducationCostDocument, EducationCostDocument.id == EducationCostAllocation.cost_document_id)
     .where(EducationCostAllocation.cohort_id.in_(cohort_ids), EducationCostDocument.active.is_(True))).subquery()
    return select(
        sources.c.cohort_id, func.sum(sources.c.income).label("income"), func.sum(sources.c.expense).label("expense"),
    ).group_by(sources.c.cohort_id).subquery()


def _enrollment_totals(cohort_ids):
    return select(EducationStudent.cohort_id.label("cohort_id"), func.count().label("count"),
        func.sum(EducationStudent.receivable).label("receivable"),
        func.sum(EducationStudent.received).label("received"),
        func.sum(case((EducationStudent.receivable > EducationStudent.received, EducationStudent.receivable - EducationStudent.received), else_=0)).label("arrears"),
    ).where(EducationStudent.cohort_id.in_(cohort_ids)).group_by(EducationStudent.cohort_id).subquery()


@router.get("/cohorts")
def list_cohorts(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                 user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _require_access(user)
    scoped = _scope(user).subquery()
    totals = _totals(db, select(scoped.c.id))
    enrolled = _enrollment_totals(select(scoped.c.id))
    summary = db.execute(select(
        func.count(scoped.c.id), func.coalesce(func.sum(func.coalesce(enrolled.c.count, scoped.c.student_count)), 0),
        func.coalesce(func.sum(func.coalesce(enrolled.c.receivable, scoped.c.student_count * scoped.c.unit_price)), 0),
        func.coalesce(func.sum(totals.c.income), 0), func.coalesce(func.sum(totals.c.expense), 0),
        func.coalesce(func.sum(enrolled.c.receivable), 0), func.coalesce(func.sum(enrolled.c.received), 0),
        func.coalesce(func.sum(enrolled.c.arrears), 0),
    ).select_from(scoped).outerjoin(totals, totals.c.cohort_id == scoped.c.id)
        .outerjoin(enrolled, enrolled.c.cohort_id == scoped.c.id)).one()
    rows = db.execute(select(EducationCohort, User.display_name, totals.c.income, totals.c.expense, enrolled.c.count, enrolled.c.receivable)
        .join(User, User.id == EducationCohort.owner_user_id)
        .outerjoin(totals, totals.c.cohort_id == EducationCohort.id)
        .outerjoin(enrolled, enrolled.c.cohort_id == EducationCohort.id)
        .where(EducationCohort.id.in_(select(scoped.c.id)))
        .order_by(EducationCohort.start_date.desc(), EducationCohort.id).offset(offset).limit(limit)).all()
    return {"items": [{**_cohort_data(row), "owner_name": owner,
                       "enrollment_count": count or 0, "effective_student_count": count if count is not None else row.student_count,
                       "expected_income": _money(due) if count is not None else _money(row.unit_price * row.student_count),
                       "income": _money(income), "expense": _money(expense),
                       "net": _money((income or 0) - (expense or 0))} for row, owner, income, expense, count, due in rows],
            "summary": {"cohort_count": summary[0], "student_count": summary[1], "expected_income": _money(summary[2]),
                        "income": _money(summary[3]), "expense": _money(summary[4]), "net": _money(summary[3] - summary[4])},
            "enrollment_summary": {"receivable": _money(summary[5]), "received": _money(summary[6]), "arrears": _money(summary[7])},
            "has_more": offset + len(rows) < summary[0], "can_edit": user.organization_role == "education" or _management(user),
            "can_delete": _reviewer_slot(user) == "founder",
            "scope": "mine" if user.organization_role == "education" else "all"}


@router.post("/cohorts")
def create_cohort(payload: CohortCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _require_access(user, write=True)
    existing = db.get(EducationCohort, str(payload.request_id))
    if existing:
        if existing.deleted_at is not None:
            raise HTTPException(409, "该提交对应班期已删除，请刷新后新建")
        if existing.owner_user_id != user.id or any(
            getattr(existing, key) != value for key, value in payload.model_dump(exclude={"request_id"}).items()
        ):
            raise HTTPException(409, "提交标识冲突，请刷新后重试")
        return {"id": existing.id}
    entity = db.scalar(select(BusinessEntity).where(BusinessEntity.name == "星曜电竞", BusinessEntity.active.is_(True)))
    if entity is None:
        raise HTTPException(409, "星曜电竞公司主体尚未启用，请联系管理员")
    row = EducationCohort(id=str(payload.request_id), entity_id=entity.id, owner_user_id=user.id,
        **payload.model_dump(exclude={"request_id"}), end_date=month_end(payload.start_date, payload.course_period), version=1)
    db.add(row)
    _audit(db, user, "education_cohort_created", None, _cohort_data(row))
    _commit(db)
    return {"id": row.id}


@router.get("/cohorts/{cohort_id}")
def cohort_detail(cohort_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    row = _cohort(db, user, cohort_id)
    entries = db.scalars(select(EducationCashEntry).where(EducationCashEntry.cohort_id == row.id)
                        .order_by(EducationCashEntry.occurred_on.desc(), EducationCashEntry.created_at.desc())).all()
    income = sum((entry.amount for entry in entries if entry.direction == "income"), Decimal(0))
    expense = sum((entry.amount for entry in entries if entry.direction == "expense"), Decimal(0))
    students = db.execute(select(func.count(), func.coalesce(func.sum(EducationStudent.receivable), 0),
        func.coalesce(func.sum(EducationStudent.received), 0), func.coalesce(func.sum(EducationStudent.cost), 0))
        .where(EducationStudent.cohort_id == row.id)).one()
    income += students[2]
    expense += students[3]
    expense += db.scalar(select(func.coalesce(func.sum(EducationCostAllocation.amount), 0))
        .join(EducationCostDocument, EducationCostDocument.id == EducationCostAllocation.cost_document_id)
        .where(EducationCostAllocation.cohort_id == row.id, EducationCostDocument.active.is_(True))) or Decimal(0)
    return {**_cohort_data(row), "owner_name": db.scalar(select(User.display_name).where(User.id == row.owner_user_id)),
            "enrollment_count": students[0], "effective_student_count": students[0] if students[0] else row.student_count,
            "expected_income": _money(students[1]) if students[0] else _money(row.unit_price * row.student_count),
            "income": _money(income), "expense": _money(expense), "net": _money(income - expense),
            "entries": [_entry_data(entry) for entry in entries]}


@router.patch("/cohorts/{cohort_id}")
def update_cohort(cohort_id: str, payload: CohortUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    row = _cohort(db, user, cohort_id, write=True)
    if row.version != payload.version:
        raise HTTPException(409, "班期已更新，请刷新后重新修改")
    before = _cohort_data(row)
    for key, value in payload.model_dump(exclude={"version"}).items():
        setattr(row, key, value)
    row.end_date = month_end(row.start_date, row.course_period)
    row.version += 1
    _audit(db, user, "education_cohort_updated", before, _cohort_data(row))
    _commit(db)
    return {"id": row.id}


@router.get("/cohorts/{cohort_id}/entries")
def list_entries(cohort_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id)
    rows = db.scalars(select(EducationCashEntry).where(EducationCashEntry.cohort_id == cohort.id)
                      .order_by(EducationCashEntry.occurred_on.desc(), EducationCashEntry.created_at.desc())).all()
    return {"items": [_entry_data(row) for row in rows]}


@router.post("/cohorts/{cohort_id}/founder-delete")
def delete_cohort(cohort_id: str, payload: CohortDelete, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_project_founder(user)
    row = _cohort(db, user, cohort_id, write=True)
    if row.version != payload.version or payload.confirm_name.strip() != row.name:
        raise HTTPException(409, "班期已更新或确认名称不一致，请刷新核对")
    if not payload.reason.strip() or len(payload.reason.strip()) < 2:
        raise HTTPException(422, "请填写删除原因")
    if not user.project_delete_password_hash:
        raise HTTPException(409, "请先设置创始人删除密码（与项目删除共用）")
    rate_key = _check_delete_rate_limit(user, "delete")
    if not verify_password(payload.deletion_password, user.project_delete_password_hash):
        project_delete_rate_limiter.record_failure(rate_key)
        _audit(db, user, "education_cohort_delete_failed", None, {"cohort_id": row.id, "result": "password_verification_failed"})
        _commit(db)
        raise HTTPException(403, "删除密码错误")
    row.deleted_at = datetime.now(timezone.utc)
    row.version += 1
    _audit(db, user, "education_cohort_deleted", None, {"cohort_id": row.id, "name": row.name,
        "reason": payload.reason.strip(), "deletion_mode": "soft_delete", "version": row.version})
    _commit(db)
    project_delete_rate_limiter.record_success(rate_key)
    return {"id": row.id, "status": "deleted", "deletion_mode": "soft_delete"}


@router.post("/cohorts/{cohort_id}/entries")
def create_entry(cohort_id: str, payload: EntryCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id, write=True)
    values = _entry_fields(db, cohort.id, payload)
    existing = db.get(EducationCashEntry, str(payload.request_id))
    if existing:
        if existing.cohort_id != cohort.id or existing.created_by_user_id != user.id or any(
            getattr(existing, key) != value for key, value in values.items()
        ):
            raise HTTPException(409, "提交标识冲突，请刷新后重试")
        return {"id": existing.id}
    row = EducationCashEntry(id=str(payload.request_id), cohort_id=cohort.id, created_by_user_id=user.id,
                             **values, version=1)
    db.add(row)
    _audit(db, user, "education_entry_created", None, _entry_data(row))
    _commit(db)
    return {"id": row.id}


@router.patch("/cohorts/{cohort_id}/entries/{entry_id}")
def update_entry(cohort_id: str, entry_id: str, payload: EntryUpdate,
                 user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id, write=True)
    row = db.scalar(select(EducationCashEntry).where(EducationCashEntry.id == entry_id, EducationCashEntry.cohort_id == cohort.id))
    if row is None:
        raise HTTPException(404, "收支记录不存在")
    if row.version != payload.version:
        raise HTTPException(409, "收支记录已更新，请刷新后重新修改")
    values = _entry_fields(db, cohort.id, payload, previous=row)
    before = _entry_data(row)
    for key, value in values.items():
        setattr(row, key, value)
    row.version += 1
    _audit(db, user, "education_entry_updated", before, _entry_data(row))
    _commit(db)
    return {"id": row.id}
