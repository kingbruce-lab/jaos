"""Local, owner-scoped enrollment records. Never indexed or sent to models."""
from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .auth import current_user
from .database import get_db
from .education_catalog import FEE_DETAILS, GAMES, PERIODS, ROOMS, STAFF_ROLES
from .education_system import _audit, _cohort, _commit, _money, _require_access, month_end
from .models import EducationPayment, EducationStaff, EducationStudent, User

router = APIRouter(prefix="/v1/pm/education", tags=["education-enrollment"])


class FeeLine(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: str
    detail: str
    staff_id: UUID | None = None
    receivable: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    cost: Decimal = Field(default=Decimal(0), ge=0, max_digits=12, decimal_places=2)
    note: str = Field(default="", max_length=500)


class StaffAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    staff_id: UUID
    start_date: date | None = None
    end_date: date | None = None
    note: str = Field(default="", max_length=500)


class StudentFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    registration_date: date
    name: str = Field(min_length=1, max_length=80)
    gender: Literal["男", "女", "未填写"]
    age: int | None = Field(default=None, ge=0, le=120, strict=True)
    birth_date: date | None = None
    identity_number: str | None = Field(default=None, max_length=32)
    phone: str | None = Field(default=None, max_length=30)
    guardian_name: str = Field(default="", max_length=80)
    guardian_phone: str | None = Field(default=None, max_length=30)
    emergency_contact: str = Field(default="", max_length=240)
    health_notes: str = Field(default="", max_length=2000)
    referrer_name: str = Field(default="", max_length=120)
    referral_channel: str = Field(default="", max_length=160)
    game: Literal["王者荣耀", "英雄联盟", "三角洲行动", "无畏契约", "CS2"]
    game_account: str = Field(default="", max_length=100)
    current_rank: str = Field(default="", max_length=100)
    course_period: Literal["8_days", "1_month", "3_months"]
    study_start: date
    accommodation_days: int = Field(ge=0, le=366, strict=True)
    room_type: Literal["一人间", "两人间"]
    fee_notes: str = Field(default="", max_length=2000)
    fees: list[FeeLine] = Field(default_factory=list, max_length=100)
    staff_assignments: list[StaffAssignment] = Field(default_factory=list, max_length=100)
    received: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=2)
    notes: str = Field(default="", max_length=2000)
    learning_status: Literal["已报名", "待入营", "在读", "已结营", "已退营"] = "已报名"

    @field_validator("registration_date", "study_start", "birth_date")
    @classmethod
    def valid_date(cls, value):
        if value is not None and not 1900 <= value.year <= 2100:
            raise ValueError("日期须在 2000 至 2100 年之间")
        return value

    @field_validator("identity_number")
    @classmethod
    def valid_identity(cls, value):
        if value and not re.fullmatch(r"(?:\d{15}|\d{17}[\dXx])", value):
            raise ValueError("身份证号须为15位数字或18位号码（末位可为X），也可暂不填写")
        return value.upper() if value else value

    @field_validator("phone", "guardian_phone")
    @classmethod
    def valid_phone(cls, value):
        if value and not re.fullmatch(r"[+\d][\d ()-]{5,28}\d", value):
            raise ValueError("请填写有效联系电话，也可暂不填写")
        return value

    @model_validator(mode="after")
    def derive_age(self):
        if self.birth_date:
            if self.birth_date > self.study_start:
                raise ValueError("出生日期不能晚于学习开始日期")
            self.age = self.study_start.year - self.birth_date.year - (
                (self.study_start.month, self.study_start.day) < (self.birth_date.month, self.birth_date.day)
            )
        if self.age is None:
            raise ValueError("请填写出生日期；历史资料也可暂填年龄")
        if self.age < 18 and self.birth_date and (not self.guardian_name or not self.guardian_phone):
            raise ValueError("未成年学员须填写监护人姓名和电话")
        return self


class StudentCreate(StudentFields):
    request_id: UUID


class StudentUpdate(StudentFields):
    version: int = Field(ge=1)


class StaffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def other_teacher_needs_note(self):
        if self.role == "其他教师" and not self.note:
            raise ValueError("其他教师请在人员备注中注明具体类型或职责")
        return self


def _student(db, user, cohort_id, student_id, *, write=False):
    _cohort(db, user, cohort_id, write=write)
    row = db.scalar(select(EducationStudent).where(EducationStudent.id == student_id, EducationStudent.cohort_id == cohort_id))
    if row is None:
        raise HTTPException(404, "学员记录不存在或无权访问")
    return row


def _mask(value):
    return (value[:3] + "*" * max(len(value) - 7, 4) + value[-4:]) if len(value) > 7 else "*" * len(value)


def _data(row, *, fees=True, private=False):
    result = {key: getattr(row, key) for key in (
        "id", "cohort_id", "student_no", "name", "gender", "age", "game", "game_account", "current_rank",
        "course_period", "accommodation_days", "room_type", "fee_notes", "notes", "learning_status", "version",
        "referrer_name", "referral_channel",
    )}
    result.update(registration_date=row.registration_date.isoformat(), study_start=row.study_start.isoformat(),
                  study_end=month_end(row.study_start, row.course_period).isoformat())
    result["birth_date"] = row.birth_date.isoformat() if row.birth_date else None
    result.update(identity_masked=_mask(row.identity_number), phone_masked=_mask(row.phone),
        guardian_phone_masked=_mask(row.guardian_phone),
        receivable=_money(row.receivable), received=_money(row.received), cost=_money(row.cost),
        arrears=_money(max(row.receivable - row.received, Decimal(0))),
        overpayment=_money(max(row.received - row.receivable, Decimal(0))))
    if private:
        result.update(guardian_name=row.guardian_name, emergency_contact=row.emergency_contact,
                      health_notes=row.health_notes)
    if fees:
        result["fees"] = json.loads(row.fees_json)
    result["staff_assignments"] = json.loads(row.staff_assignments_json or "[]")
    return result


def _values(db, cohort_id, payload, previous=None):
    previous_staff = {item.get("staff_id") for item in json.loads(previous.fees_json)} if previous else set()
    previous_assignments = {item.get("staff_id") for item in json.loads(previous.staff_assignments_json or "[]")} if previous else set()
    fees = []
    for item in payload.fees:
        if item.category not in FEE_DETAILS or item.detail not in FEE_DETAILS[item.category]:
            raise HTTPException(422, "费用分类或明细无效")
        if item.category != "学费" and item.receivable > 0:
            raise HTTPException(422, "学费为包含住宿餐饮的一口价套餐；其他费用行只能登记公司成本")
        staff_id = str(item.staff_id) if item.staff_id else None
        staff = db.get(EducationStaff, staff_id) if staff_id else None
        if item.category == "人员成本":
            if staff is None or staff.cohort_id != cohort_id or staff.role != item.detail:
                raise HTTPException(422, "人员成本须选择本班期对应类型的教师或助教")
            if not staff.active and staff_id not in previous_staff:
                raise HTTPException(422, "该人员已移除，请选择在册人员")
        elif staff_id:
            raise HTTPException(422, "仅人员成本可关联人员")
        fees.append({"category": item.category, "detail": item.detail, "staff_id": staff_id,
                     "receivable": _money(item.receivable), "cost": _money(item.cost), "note": item.note})
    study_end = month_end(payload.study_start, payload.course_period)
    assignments = []
    assigned_ids = set()
    for item in payload.staff_assignments:
        staff_id = str(item.staff_id)
        if staff_id in assigned_ids:
            raise HTTPException(422, "同一学员不能重复添加同一位人员")
        assigned_ids.add(staff_id)
        staff = db.get(EducationStaff, staff_id)
        if staff is None or staff.cohort_id != cohort_id:
            raise HTTPException(422, "授课人员须从本班期人员名册中选择")
        if not staff.active and staff_id not in previous_assignments:
            raise HTTPException(422, "该人员已移除，请选择在册人员")
        start_date = item.start_date or payload.study_start
        end_date = item.end_date or study_end
        if start_date > end_date or start_date < payload.study_start or end_date > study_end:
            raise HTTPException(422, "人员负责期间须在学员学习开始和结束日期内")
        assignments.append({"staff_id": staff_id, "name": staff.name, "role": staff.role,
                            "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
                            "note": item.note or staff.note})
    result = payload.model_dump(exclude={"request_id", "version", "fees", "staff_assignments", "identity_number", "phone", "guardian_phone"})
    result.update(fees_json=json.dumps(fees, ensure_ascii=False),
        staff_assignments_json=json.dumps(assignments, ensure_ascii=False), study_end=study_end,
        receivable=sum((item.receivable for item in payload.fees), Decimal(0)),
        cost=sum((item.cost for item in payload.fees), Decimal(0)))
    for field in ("identity_number", "phone", "guardian_phone"):
        value = getattr(payload, field)
        if value is not None:
            result[field] = value
    return result


def _audit_student(db, user, action, row, changed_fields):
    # Never duplicate ID numbers, telephone numbers or free-text notes in audit logs.
    _audit(db, user, action, None, {"student_id": row.id, "cohort_id": row.cohort_id,
        "version": row.version, "changed_fields": sorted(changed_fields),
        "receivable": _money(row.receivable), "received": _money(row.received), "cost": _money(row.cost)})


@router.get("/options")
def options(user: User = Depends(current_user)):
    _require_access(user)
    return {"games": GAMES, "periods": PERIODS, "rooms": ROOMS, "staff_roles": STAFF_ROLES, "fee_details": FEE_DETAILS}


@router.get("/cohorts/{cohort_id}/staff")
def list_staff(cohort_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _cohort(db, user, cohort_id)
    return {"items": [{"id": row.id, "name": row.name, "role": row.role, "note": row.note, "active": row.active} for row in db.scalars(
        select(EducationStaff).where(EducationStaff.cohort_id == cohort_id).order_by(EducationStaff.created_at, EducationStaff.name)).all()]}


@router.post("/cohorts/{cohort_id}/staff")
def create_staff(cohort_id: str, payload: StaffCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _cohort(db, user, cohort_id, write=True)
    if payload.role not in STAFF_ROLES:
        raise HTTPException(422, "人员类型无效")
    row = db.get(EducationStaff, str(payload.request_id))
    if row:
        if row.cohort_id != cohort_id or row.name != payload.name or row.role != payload.role or row.note != payload.note:
            raise HTTPException(409, "提交标识冲突")
        return {"id": row.id}
    row = EducationStaff(id=str(payload.request_id), cohort_id=cohort_id, created_by_user_id=user.id,
                         name=payload.name, role=payload.role, note=payload.note)
    db.add(row)
    _audit(db, user, "education_staff_created", None, {"staff_id": row.id, "cohort_id": cohort_id, "role": row.role})
    _commit(db)
    return {"id": row.id}


@router.delete("/cohorts/{cohort_id}/staff/{staff_id}")
def remove_staff(cohort_id: str, staff_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _cohort(db, user, cohort_id, write=True)
    row = db.scalar(select(EducationStaff).where(EducationStaff.id == staff_id, EducationStaff.cohort_id == cohort_id))
    if row is None:
        raise HTTPException(404, "人员不存在或无权操作")
    if row.active:
        row.active = False
        _audit(db, user, "education_staff_removed", {"active": True}, {"staff_id": row.id, "cohort_id": cohort_id, "active": False})
        _commit(db)
    return {"id": row.id, "active": False}


@router.get("/cohorts/{cohort_id}/students")
def list_students(cohort_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    _cohort(db, user, cohort_id)
    where = EducationStudent.cohort_id == cohort_id
    totals = db.execute(select(func.count(), func.coalesce(func.sum(EducationStudent.receivable), 0),
        func.coalesce(func.sum(EducationStudent.received), 0), func.coalesce(func.sum(EducationStudent.cost), 0),
        func.coalesce(func.sum(case((EducationStudent.receivable > EducationStudent.received,
            EducationStudent.receivable - EducationStudent.received), else_=0)), 0)).where(where)).one()
    rows = db.scalars(select(EducationStudent).where(where).order_by(EducationStudent.registration_date.desc(), EducationStudent.id)
                      .offset(offset).limit(limit)).all()
    return {"items": [_data(row, fees=False) for row in rows], "has_more": offset + len(rows) < totals[0],
            "summary": {"count": totals[0], "receivable": _money(totals[1]), "received": _money(totals[2]), "cost": _money(totals[3]), "arrears": _money(totals[4])}}


@router.get("/cohorts/{cohort_id}/students/{student_id}")
def student_detail(cohort_id: str, student_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _data(_student(db, user, cohort_id, student_id), private=user.organization_role != "finance")


@router.post("/cohorts/{cohort_id}/students")
def create_student(cohort_id: str, payload: StudentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _cohort(db, user, cohort_id, write=True)
    values = _values(db, cohort_id, payload)
    values.setdefault("identity_number", "")
    values.setdefault("phone", "")
    values.setdefault("guardian_phone", "")
    existing = db.get(EducationStudent, str(payload.request_id))
    if existing:
        if existing.cohort_id != cohort_id or any(getattr(existing, key) != value for key, value in values.items()):
            raise HTTPException(409, "记录已提交或发生变化，请刷新确认")
        return {"id": existing.id}
    row = EducationStudent(id=str(payload.request_id), cohort_id=cohort_id, created_by_user_id=user.id,
        student_no=f"XY{payload.registration_date:%y%m%d}{payload.request_id.hex[-6:].upper()}", version=1, **values)
    db.add(row)
    _audit_student(db, user, "education_student_created", row, values.keys())
    _commit(db)
    return {"id": row.id}


@router.patch("/cohorts/{cohort_id}/students/{student_id}")
def update_student(cohort_id: str, student_id: str, payload: StudentUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _student(db, user, cohort_id, student_id, write=True)
    if row.version != payload.version:
        raise HTTPException(409, "学员记录已更新，请刷新后重新修改")
    if payload.received != row.received and db.scalar(select(EducationPayment.id).where(EducationPayment.student_id == row.id).limit(1)):
        raise HTTPException(422, "已有收退款明细，净实收只能通过逐笔收退款记录调整")
    values = _values(db, cohort_id, payload, previous=row)
    changed = [key for key, value in values.items() if getattr(row, key) != value]
    for key, value in values.items():
        setattr(row, key, value)
    row.version += 1
    _audit_student(db, user, "education_student_updated", row, changed)
    _commit(db)
    return {"id": row.id}


@router.post("/cohorts/{cohort_id}/students/{student_id}/identity")
def reveal_identity(cohort_id: str, student_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = _student(db, user, cohort_id, student_id, write=True)
    _audit_student(db, user, "education_student_identity_viewed", row, [])
    _commit(db)
    return JSONResponse({"identity_number": row.identity_number, "phone": row.phone,
        "guardian_phone": row.guardian_phone}, headers={"Cache-Control": "no-store"})
