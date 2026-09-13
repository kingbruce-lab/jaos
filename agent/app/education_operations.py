"""Education cost allocation, 6+1 calendars and auditable daily operations logs."""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .auth import current_user
from .database import get_db
from .education_catalog import FEE_DETAILS
from .education_system import _audit, _cohort, _commit, _money, _scope
from .models import (
    EducationCostAllocation,
    EducationCostDocument,
    EducationCohort,
    EducationDailyLog,
    EducationScheduleDay,
    EducationStaff,
    EducationStudent,
    User,
)

router = APIRouter(prefix="/v1/pm/education", tags=["education-operations"])

COST_CATEGORIES = {key for key in FEE_DETAILS if key != "学费"}
LOG_TYPES = {"教学记录", "自主练习", "考勤记录", "生活管理", "异常事件"}


class CostDocumentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    request_id: UUID
    occurred_on: date
    ended_on: date | None = None
    category: str = Field(min_length=1, max_length=40)
    detail: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    vendor: str = Field(default="", max_length=240)
    document_no: str = Field(default="", max_length=120)
    source_ref: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=2000)
    allocation_mode: Literal["cohort", "equal_students", "custom"] = "cohort"
    allocation_month: date | None = None
    allocations: list["CostAllocationInput"] = Field(default_factory=list, max_length=500)

    @field_validator("allocation_month")
    @classmethod
    def month_must_be_first(cls, value: date | None) -> date | None:
        if value is not None and value.day != 1:
            raise ValueError("分摊月份必须选择当月第一天")
        return value

    @model_validator(mode="after")
    def valid_period(self):
        if self.ended_on and self.ended_on < self.occurred_on:
            raise ValueError("结束日期不能早于发生日期")
        return self


class CostAllocationInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    cohort_id: UUID
    student_id: UUID | None = None
    allocation_month: date
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    note: str = Field(default="", max_length=1000)

    @field_validator("allocation_month")
    @classmethod
    def month_must_be_first(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("分摊月份必须选择当月第一天")
        return value


class CostDocumentUpdate(CostDocumentCreate):
    request_id: UUID | None = Field(default=None, exclude=True)
    version: int = Field(ge=1)


class ScheduleReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    instructor_ids: list[UUID] = Field(default_factory=list, max_length=30)
    student_ids: list[UUID] = Field(default_factory=list, max_length=200)
    attendance: str = Field(default="", max_length=2000)
    lesson_objectives: str = Field(default="", max_length=3000)
    lesson_content: str = Field(default="", max_length=5000)
    student_performance: str = Field(default="", max_length=5000)
    issues_and_adjustments: str = Field(default="", max_length=5000)
    homework_or_practice: str = Field(default="", max_length=3000)
    parent_communication: str = Field(default="", max_length=3000)
    next_plan: str = Field(default="", max_length=3000)


class ScheduleDayUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    day_type: Literal["teaching", "practice", "rest"]
    title: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=2000)
    report: ScheduleReport | None = None
    version: int = Field(ge=1)


class DailyLogCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    request_id: UUID
    log_date: date
    staff_id: UUID
    log_type: Literal["教学记录", "自主练习", "考勤记录", "生活管理", "异常事件"]
    summary: str = Field(min_length=2, max_length=5000)
    student_ids: list[UUID] = Field(default_factory=list, max_length=200)
    follow_up: str = Field(default="", max_length=3000)


class DailyLogUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    log_date: date
    staff_id: UUID
    log_type: Literal["教学记录", "自主练习", "考勤记录", "生活管理", "异常事件"]
    summary: str = Field(min_length=2, max_length=5000)
    student_ids: list[UUID] = Field(default_factory=list, max_length=200)
    follow_up: str = Field(default="", max_length=3000)
    version: int = Field(ge=1)


def _month(value: date) -> date:
    return value.replace(day=1)


def _cost_data(row: EducationCostDocument, allocations: list[dict]) -> dict:
    allocated = sum((Decimal(item["amount"]) for item in allocations), Decimal("0"))
    return {
        "id": row.id,
        "occurred_on": row.occurred_on.isoformat(),
        "ended_on": (row.ended_on or row.occurred_on).isoformat(),
        "category": row.category,
        "detail": row.detail,
        "amount": _money(row.amount),
        "allocated_amount": _money(allocated),
        "unallocated_amount": _money(max(row.amount - allocated, Decimal("0"))),
        "vendor": row.vendor,
        "document_no": row.document_no,
        "source_ref": row.source_ref,
        "note": row.note,
        "version": row.version,
        "allocations": allocations,
    }


def _cost_allocations(db: Session, document_id: str, cohort_ids: set[str] | None = None) -> list[dict]:
    query = (
        select(EducationCostAllocation, EducationStudent.name, EducationCohort.name)
        .outerjoin(EducationStudent, EducationStudent.id == EducationCostAllocation.student_id)
        .join(EducationCohort, EducationCohort.id == EducationCostAllocation.cohort_id)
        .where(EducationCostAllocation.cost_document_id == document_id)
        .order_by(EducationCostAllocation.allocation_month, EducationCohort.start_date, EducationCostAllocation.id)
    )
    if cohort_ids is not None:
        query = query.where(EducationCostAllocation.cohort_id.in_(cohort_ids))
    return [{
        "id": allocation.id,
        "cohort_id": allocation.cohort_id,
        "cohort_name": cohort_name,
        "student_id": allocation.student_id,
        "student_name": student_name,
        "allocation_month": allocation.allocation_month.isoformat(),
        "amount": _money(allocation.amount),
        "note": allocation.note,
    } for allocation, student_name, cohort_name in db.execute(query).all()]


def _day_data(row: EducationScheduleDay, include_report: bool = True) -> dict:
    try:
        report = json.loads(row.report_json or "{}") if include_report else {}
    except (TypeError, json.JSONDecodeError):
        report = {}
    return {
        "id": row.id,
        "calendar_date": row.calendar_date.isoformat(),
        "day_number": row.day_number,
        "day_type": row.day_type,
        "title": row.title,
        "notes": row.notes,
        "report": {
            "instructor_ids": report.get("instructor_ids", []),
            "student_ids": report.get("student_ids", []),
            "attendance": report.get("attendance", ""),
            "lesson_objectives": report.get("lesson_objectives", ""),
            "lesson_content": report.get("lesson_content", ""),
            "student_performance": report.get("student_performance", ""),
            "issues_and_adjustments": report.get("issues_and_adjustments", ""),
            "homework_or_practice": report.get("homework_or_practice", ""),
            "parent_communication": report.get("parent_communication", ""),
            "next_plan": report.get("next_plan", ""),
        },
        "version": row.version,
    }


def _validate_schedule_report(db: Session, cohort_id: str, report: ScheduleReport) -> dict:
    instructor_ids = [str(item) for item in dict.fromkeys(report.instructor_ids)]
    student_ids = [str(item) for item in dict.fromkeys(report.student_ids)]
    if instructor_ids:
        valid_staff = set(db.scalars(select(EducationStaff.id).where(
            EducationStaff.cohort_id == cohort_id,
            EducationStaff.id.in_(instructor_ids),
            EducationStaff.active.is_(True),
        )).all())
        if valid_staff != set(instructor_ids):
            raise HTTPException(422, "日报包含不属于本班期的在册教师或助教")
    if student_ids:
        valid_students = set(db.scalars(select(EducationStudent.id).where(
            EducationStudent.cohort_id == cohort_id,
            EducationStudent.id.in_(student_ids),
        )).all())
        if valid_students != set(student_ids):
            raise HTTPException(422, "日报包含不属于本班期的学员")
    result = report.model_dump(mode="json")
    result["instructor_ids"] = instructor_ids
    result["student_ids"] = student_ids
    return result


def _log_data(row: EducationDailyLog, staff_name: str, staff_role: str) -> dict:
    return {
        "id": row.id,
        "log_date": row.log_date.isoformat(),
        "schedule_day_id": row.schedule_day_id,
        "staff_id": row.staff_id,
        "staff_name": staff_name,
        "staff_role": staff_role,
        "log_type": row.log_type,
        "summary": row.summary,
        "student_ids": json.loads(row.student_ids_json or "[]"),
        "follow_up": row.follow_up,
        "version": row.version,
    }


def _split_evenly(amount: Decimal, count: int) -> list[Decimal]:
    cents = int((amount * 100).to_integral_value(rounding=ROUND_DOWN))
    quotient, remainder = divmod(cents, count)
    return [Decimal(quotient + (1 if index < remainder else 0)) / 100 for index in range(count)]


def _validate_log_targets(db: Session, cohort, payload: DailyLogCreate | DailyLogUpdate) -> tuple[EducationStaff, list[str], str | None]:
    if not cohort.start_date <= payload.log_date <= cohort.end_date:
        raise HTTPException(422, "记录日期必须在本班期内")
    staff = db.get(EducationStaff, str(payload.staff_id))
    if staff is None or staff.cohort_id != cohort.id or not staff.active:
        raise HTTPException(422, "请选择本班期在册教师或助教")
    student_ids = [str(item) for item in dict.fromkeys(payload.student_ids)]
    if student_ids:
        valid = set(db.scalars(select(EducationStudent.id).where(EducationStudent.cohort_id == cohort.id, EducationStudent.id.in_(student_ids))).all())
        if valid != set(student_ids):
            raise HTTPException(422, "日志包含不属于本班期的学员")
    schedule_day_id = db.scalar(select(EducationScheduleDay.id).where(
        EducationScheduleDay.cohort_id == cohort.id,
        EducationScheduleDay.calendar_date == payload.log_date,
    ))
    return staff, student_ids, schedule_day_id


def _allocation_targets(db: Session, user: User, base_cohort, payload: CostDocumentCreate | CostDocumentUpdate) -> list[tuple[str, str | None, date, Decimal, str]]:
    default_month = payload.allocation_month or _month(payload.occurred_on)
    if payload.allocation_mode == "cohort":
        return [(base_cohort.id, None, default_month, payload.amount, payload.note)]
    if payload.allocation_mode == "equal_students":
        students = db.scalars(
            select(EducationStudent)
            .where(EducationStudent.cohort_id == base_cohort.id, EducationStudent.learning_status != "已退营")
            .order_by(EducationStudent.student_no, EducationStudent.id)
        ).all()
        if not students:
            raise HTTPException(409, "本班期尚无可分摊学员，请先登记学员或改为班期公共成本")
        return [
            (base_cohort.id, student.id, default_month, part, payload.note)
            for student, part in zip(students, _split_evenly(payload.amount, len(students)), strict=True)
        ]
    if not payload.allocations:
        raise HTTPException(422, "自定义分摊至少需要一条分摊明细")
    if sum((item.amount for item in payload.allocations), Decimal("0")) != payload.amount:
        raise HTTPException(422, "自定义分摊金额合计必须等于原始单据金额")
    seen: set[tuple[str, str | None, date]] = set()
    targets: list[tuple[str, str | None, date, Decimal, str]] = []
    for item in payload.allocations:
        cohort_id = str(item.cohort_id)
        target_cohort = _cohort(db, user, cohort_id, write=True)
        if target_cohort.entity_id != base_cohort.entity_id:
            raise HTTPException(422, "成本只能在同一公司主体的班期之间分摊")
        student_id = str(item.student_id) if item.student_id else None
        if student_id:
            student = db.get(EducationStudent, student_id)
            if student is None or student.cohort_id != target_cohort.id:
                raise HTTPException(422, "分摊学员不属于所选班期")
        key = (target_cohort.id, student_id, item.allocation_month)
        if key in seen:
            raise HTTPException(422, "同一班期、学员和月份不能重复分摊")
        seen.add(key)
        targets.append((target_cohort.id, student_id, item.allocation_month, item.amount, item.note))
    return targets


@router.get("/cohorts/{cohort_id}/operations")
def operations(
    cohort_id: str,
    log_type: str | None = Query(None, max_length=24),
    staff_id: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    user: User = Depends(current_user), db: Session = Depends(get_db),
) -> dict:
    cohort = _cohort(db, user, cohort_id)
    days = db.scalars(
        select(EducationScheduleDay)
        .where(EducationScheduleDay.cohort_id == cohort.id)
        .order_by(EducationScheduleDay.calendar_date)
    ).all()

    allocation_rows = db.execute(
        select(EducationCostAllocation, EducationCostDocument, EducationStudent.name)
        .join(EducationCostDocument, EducationCostDocument.id == EducationCostAllocation.cost_document_id)
        .outerjoin(EducationStudent, EducationStudent.id == EducationCostAllocation.student_id)
        .where(EducationCostAllocation.cohort_id == cohort.id, EducationCostDocument.active.is_(True))
        .order_by(EducationCostDocument.occurred_on.desc(), EducationCostDocument.created_at.desc())
    ).all()
    grouped: dict[str, tuple[EducationCostDocument, list[dict]]] = {}
    for allocation, document, student_name in allocation_rows:
        grouped.setdefault(document.id, (document, []))[1].append({
            "id": allocation.id,
            "cohort_id": allocation.cohort_id,
            "student_id": allocation.student_id,
            "student_name": student_name,
            "allocation_month": allocation.allocation_month.isoformat(),
            "amount": _money(allocation.amount),
            "note": allocation.note,
        })

    can_view_logs = user.organization_role != "finance"
    logs: list[dict] = []
    missing_log_days: list[str] = []
    if can_view_logs:
        log_query = (
            select(EducationDailyLog, EducationStaff.name, EducationStaff.role)
            .join(EducationStaff, EducationStaff.id == EducationDailyLog.staff_id)
            .where(EducationDailyLog.cohort_id == cohort.id)
        )
        if log_type:
            if log_type not in LOG_TYPES:
                raise HTTPException(422, "请选择有效的记录类型")
            log_query = log_query.where(EducationDailyLog.log_type == log_type)
        if staff_id:
            log_query = log_query.where(EducationDailyLog.staff_id == staff_id)
        if from_date:
            log_query = log_query.where(EducationDailyLog.log_date >= from_date)
        if to_date:
            log_query = log_query.where(EducationDailyLog.log_date <= to_date)
        logs = [
            _log_data(row, staff_name, staff_role)
            for row, staff_name, staff_role in db.execute(
                log_query
                .order_by(EducationDailyLog.log_date.desc(), EducationDailyLog.created_at.desc())
                .limit(100)
            ).all()
        ]
        cutoff = min(date.today(), cohort.end_date)
        missing_log_days = [
            day.calendar_date.isoformat() for day in days
            if day.calendar_date <= cutoff and day.day_type != "rest"
            and not any(_day_data(day)["report"].get(key) for key in (
                "attendance", "lesson_objectives", "lesson_content", "student_performance",
            ))
        ]

    costs = [_cost_data(document, allocations) for document, allocations in grouped.values()]
    return {
        "schedule": {
            "generated": bool(days),
            "days": [_day_data(day, include_report=can_view_logs) for day in days],
            "summary": {
                "teaching": sum(day.day_type == "teaching" for day in days),
                "practice": sum(day.day_type == "practice" for day in days),
                "rest": sum(day.day_type == "rest" for day in days),
            },
        },
        "costs": {
            "items": costs,
            "source_total": _money(sum((document.amount for document, _ in grouped.values()), Decimal("0"))),
            "allocated_to_cohort": _money(sum((allocation.amount for allocation, _, _ in allocation_rows), Decimal("0"))),
        },
        "logs": logs,
        "missing_log_days": missing_log_days,
        "can_view_logs": can_view_logs,
        "can_edit": user.organization_role in {"education", "management"},
    }


@router.post("/cohorts/{cohort_id}/schedule/generate")
def generate_schedule(cohort_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id, write=True)
    existing_dates = set(db.scalars(select(EducationScheduleDay.calendar_date).where(EducationScheduleDay.cohort_id == cohort.id)).all())
    created = 0
    current = cohort.start_date
    while current <= cohort.end_date:
        offset = (current - cohort.start_date).days
        if current not in existing_dates:
            day_type = "practice" if offset % 7 == 6 else "teaching"
            db.add(EducationScheduleDay(
                cohort_id=cohort.id,
                calendar_date=current,
                day_number=offset + 1,
                day_type=day_type,
                title="自主练习" if day_type == "practice" else f"第 {offset + 1} 天课程",
                notes="",
                updated_by_user_id=user.id,
                version=1,
            ))
            created += 1
        current += timedelta(days=1)
    _audit(db, user, "education_schedule_generated", None, {"cohort_id": cohort.id, "created": created, "rule": "6+1"})
    _commit(db)
    return {"created": created, "total_days": (cohort.end_date - cohort.start_date).days + 1}


@router.patch("/cohorts/{cohort_id}/schedule/{day_id}")
def update_schedule_day(cohort_id: str, day_id: str, payload: ScheduleDayUpdate,
                        user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id, write=True)
    row = db.scalar(select(EducationScheduleDay).where(EducationScheduleDay.id == day_id, EducationScheduleDay.cohort_id == cohort.id).with_for_update())
    if row is None:
        raise HTTPException(404, "课表日期不存在")
    if row.version != payload.version:
        raise HTTPException(409, "课表已更新，请刷新后重试")
    before = _day_data(row)
    row.day_type = payload.day_type
    row.title = payload.title
    row.notes = payload.notes
    if payload.report is not None:
        row.report_json = json.dumps(_validate_schedule_report(db, cohort.id, payload.report), ensure_ascii=False)
    row.updated_by_user_id = user.id
    row.version += 1
    _audit(db, user, "education_schedule_day_updated", before, _day_data(row))
    _commit(db)
    return {"id": row.id}


@router.post("/cohorts/{cohort_id}/daily-logs")
def create_daily_log(cohort_id: str, payload: DailyLogCreate,
                     user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id, write=True)
    staff, student_ids, schedule_day_id = _validate_log_targets(db, cohort, payload)
    existing = db.get(EducationDailyLog, str(payload.request_id))
    if existing:
        if existing.cohort_id != cohort.id or existing.created_by_user_id != user.id:
            raise HTTPException(409, "提交标识冲突，请刷新后重试")
        return {"id": existing.id}
    row = EducationDailyLog(
        id=str(payload.request_id), cohort_id=cohort.id, schedule_day_id=schedule_day_id,
        log_date=payload.log_date, staff_id=staff.id, log_type=payload.log_type,
        summary=payload.summary, student_ids_json=json.dumps(student_ids), follow_up=payload.follow_up,
        created_by_user_id=user.id, version=1,
    )
    db.add(row)
    _audit(db, user, "education_daily_log_created", None, {
        "id": row.id, "cohort_id": cohort.id, "log_date": row.log_date,
        "staff_id": row.staff_id, "log_type": row.log_type, "student_count": len(student_ids),
    })
    _commit(db)
    return {"id": row.id}


@router.patch("/cohorts/{cohort_id}/daily-logs/{log_id}")
def update_daily_log(cohort_id: str, log_id: str, payload: DailyLogUpdate,
                     user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id, write=True)
    row = db.scalar(select(EducationDailyLog).where(
        EducationDailyLog.id == log_id, EducationDailyLog.cohort_id == cohort.id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "每日记录不存在")
    if row.version != payload.version:
        raise HTTPException(409, "每日记录已更新，请刷新后重试")
    staff, student_ids, schedule_day_id = _validate_log_targets(db, cohort, payload)
    before = {
        "id": row.id, "log_date": row.log_date, "staff_id": row.staff_id,
        "log_type": row.log_type, "student_count": len(json.loads(row.student_ids_json or "[]")),
        "version": row.version,
    }
    row.log_date = payload.log_date
    row.schedule_day_id = schedule_day_id
    row.staff_id = staff.id
    row.log_type = payload.log_type
    row.summary = payload.summary
    row.student_ids_json = json.dumps(student_ids)
    row.follow_up = payload.follow_up
    row.version += 1
    _audit(db, user, "education_daily_log_updated", before, {
        "id": row.id, "log_date": row.log_date, "staff_id": row.staff_id,
        "log_type": row.log_type, "student_count": len(student_ids), "version": row.version,
    })
    _commit(db)
    return {"id": row.id}


@router.post("/cohorts/{cohort_id}/cost-documents")
def create_cost_document(cohort_id: str, payload: CostDocumentCreate,
                         user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id, write=True)
    if payload.category not in COST_CATEGORIES or payload.detail not in FEE_DETAILS[payload.category]:
        raise HTTPException(422, "请选择有效的成本分类和明细；学费属于收入，不能作为成本单据")
    targets = _allocation_targets(db, user, cohort, payload)
    existing = db.get(EducationCostDocument, str(payload.request_id))
    if existing:
        existing_allocations = db.scalars(select(EducationCostAllocation).where(
            EducationCostAllocation.cost_document_id == existing.id,
        )).all()
        source_matches = (
            existing.entity_id == cohort.entity_id
            and existing.created_by_user_id == user.id
            and existing.occurred_on == payload.occurred_on
            and (existing.ended_on or existing.occurred_on) == (payload.ended_on or payload.occurred_on)
            and existing.category == payload.category
            and existing.detail == payload.detail
            and existing.amount == payload.amount
            and existing.vendor == payload.vendor
            and existing.document_no == payload.document_no
            and existing.source_ref == payload.source_ref
            and existing.note == payload.note
        )
        sort_key = lambda item: (item[0], item[1] or "", item[2], item[3], item[4])
        existing_values = sorted(
            ((item.cohort_id, item.student_id, item.allocation_month, item.amount, item.note) for item in existing_allocations),
            key=sort_key,
        )
        allocation_matches = existing_values == sorted(targets, key=sort_key)
        if not source_matches or not allocation_matches:
            raise HTTPException(409, "提交标识冲突，请刷新后重试")
        return {"id": existing.id}

    document = EducationCostDocument(
        id=str(payload.request_id), entity_id=cohort.entity_id, occurred_on=payload.occurred_on,
        ended_on=payload.ended_on or payload.occurred_on,
        category=payload.category, detail=payload.detail, amount=payload.amount,
        vendor=payload.vendor, document_no=payload.document_no, source_ref=payload.source_ref,
        note=payload.note, created_by_user_id=user.id, version=1, active=True,
    )
    db.add(document)
    for target_cohort_id, student_id, allocation_month, amount, note in targets:
        db.add(EducationCostAllocation(
            cost_document_id=document.id, cohort_id=target_cohort_id, student_id=student_id,
            allocation_month=allocation_month, amount=amount, note=note,
            created_by_user_id=user.id,
        ))
    _audit(db, user, "education_cost_document_created", None, {
        "id": document.id, "cohort_id": cohort.id, "category": document.category,
        "amount": _money(document.amount), "allocation_mode": payload.allocation_mode,
        "allocation_count": len(targets),
    })
    _commit(db)
    return {"id": document.id}


@router.get("/cohorts/{cohort_id}/cost-documents/{document_id}")
def cost_document_detail(cohort_id: str, document_id: str,
                         user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id)
    document = db.get(EducationCostDocument, document_id)
    if document is None or not document.active or document.entity_id != cohort.entity_id:
        raise HTTPException(404, "成本单据不存在")
    all_cohort_ids = set(db.scalars(select(EducationCostAllocation.cohort_id).where(
        EducationCostAllocation.cost_document_id == document.id,
    )).all())
    if cohort.id not in all_cohort_ids:
        raise HTTPException(404, "成本单据不属于当前班期")
    allowed_ids = set(db.scalars(_scope(user).with_only_columns(EducationCohort.id)).all())
    visible_ids = all_cohort_ids & allowed_ids
    allocations = _cost_allocations(db, document.id, visible_ids)
    if not allocations:
        raise HTTPException(404, "成本单据不存在或无权查看")
    result = _cost_data(document, allocations)
    same_month = {item["allocation_month"] for item in allocations}
    result.update({
        "allocation_mode": (
            "cohort" if len(allocations) == 1 and allocations[0]["student_id"] is None
            else "equal_students" if len(all_cohort_ids) == 1 and all(item["student_id"] for item in allocations)
            else "custom"
        ),
        "allocation_month": next(iter(same_month)) if len(same_month) == 1 else None,
        "can_edit": user.organization_role != "finance" and all_cohort_ids <= allowed_ids,
        "has_hidden_allocations": visible_ids != all_cohort_ids,
    })
    return result


@router.patch("/cohorts/{cohort_id}/cost-documents/{document_id}")
def update_cost_document(cohort_id: str, document_id: str, payload: CostDocumentUpdate,
                         user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id, write=True)
    document = db.scalar(select(EducationCostDocument).where(
        EducationCostDocument.id == document_id,
        EducationCostDocument.entity_id == cohort.entity_id,
        EducationCostDocument.active.is_(True),
    ).with_for_update())
    if document is None:
        raise HTTPException(404, "成本单据不存在")
    old_cohort_ids = set(db.scalars(select(EducationCostAllocation.cohort_id).where(
        EducationCostAllocation.cost_document_id == document.id,
    )).all())
    if cohort.id not in old_cohort_ids:
        raise HTTPException(404, "成本单据不属于当前班期")
    allowed_ids = set(db.scalars(_scope(user).with_only_columns(EducationCohort.id)).all())
    if not old_cohort_ids <= allowed_ids:
        raise HTTPException(403, "该单据含其他负责人班期分摊，请由L5管理修正")
    if document.version != payload.version:
        raise HTTPException(409, "成本单据已更新，请刷新后重试")
    if payload.category not in COST_CATEGORIES or payload.detail not in FEE_DETAILS[payload.category]:
        raise HTTPException(422, "请选择有效的成本分类和明细；学费属于收入，不能作为成本单据")
    targets = _allocation_targets(db, user, cohort, payload)
    before = {
        "id": document.id, "category": document.category, "detail": document.detail,
        "amount": _money(document.amount), "version": document.version,
        "allocation_count": db.scalar(select(func.count(EducationCostAllocation.id)).where(
            EducationCostAllocation.cost_document_id == document.id,
        )),
    }
    document.occurred_on = payload.occurred_on
    document.ended_on = payload.ended_on or payload.occurred_on
    document.category = payload.category
    document.detail = payload.detail
    document.amount = payload.amount
    document.vendor = payload.vendor
    document.document_no = payload.document_no
    document.source_ref = payload.source_ref
    document.note = payload.note
    document.version += 1
    db.execute(delete(EducationCostAllocation).where(EducationCostAllocation.cost_document_id == document.id))
    for target_cohort_id, student_id, allocation_month, amount, note in targets:
        db.add(EducationCostAllocation(
            cost_document_id=document.id, cohort_id=target_cohort_id, student_id=student_id,
            allocation_month=allocation_month, amount=amount, note=note, created_by_user_id=user.id,
        ))
    _audit(db, user, "education_cost_document_updated", before, {
        "id": document.id, "category": document.category, "detail": document.detail,
        "amount": _money(document.amount), "version": document.version,
        "allocation_count": len(targets),
    })
    _commit(db)
    return {"id": document.id}
