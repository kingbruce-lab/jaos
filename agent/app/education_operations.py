"""Direct-to-ledger education costs, 6+1 calendars and auditable daily logs."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .auth import current_user
from .config import settings
from .database import get_db
from .education_catalog import FEE_DETAILS
from .education_system import _audit, _cohort, _commit, _money, _scope
from .models import (
    EducationCostAllocation,
    EducationCostAttachment,
    EducationCostDocument,
    EducationCohort,
    EducationDailyLog,
    EducationScheduleDay,
    EducationMonthlySummary,
    EducationStaff,
    EducationStudent,
    User,
)

router = APIRouter(prefix="/v1/pm/education", tags=["education-operations"])

COST_CATEGORIES = {key for key in FEE_DETAILS if key != "学费"}
LOG_TYPES = {"教学记录", "自主练习", "考勤记录", "生活管理", "异常事件"}
ATTACHMENT_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".zip"}
ATTACHMENT_MAX_BYTES = 200 * 1024 * 1024


class CostDocumentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    request_id: UUID
    occurred_on: date
    ended_on: date | None = None
    category: str = Field(min_length=1, max_length=40)
    detail: str = Field(min_length=1, max_length=80)
    unit_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    vendor: str = Field(default="", max_length=240)
    document_no: str = Field(default="", max_length=120)
    source_ref: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_period(self):
        if self.ended_on and self.ended_on < self.occurred_on:
            raise ValueError("结束日期不能早于发生日期")
        return self


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
    special_achievement: bool = False
    special_achievement_note: str = Field(default="", max_length=2000)
    problem_flag: bool = False
    problem_note: str = Field(default="", max_length=2000)


class ScheduleDayUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    day_type: Literal["teaching", "practice", "rest"]
    title: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=2000)
    report: ScheduleReport | None = None
    version: int = Field(ge=1)


class MonthlySummaryUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    summary: str = Field(default="", max_length=8000)
    achievements: str = Field(default="", max_length=5000)
    problems: str = Field(default="", max_length=5000)
    next_month_plan: str = Field(default="", max_length=5000)
    version: int = Field(ge=0)


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


def _attachment_data(row: EducationCostAttachment) -> dict:
    return {
        "id": row.id,
        "filename": row.filename,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "created_at": row.created_at,
    }


def _cost_data(row: EducationCostDocument, allocations: list[dict], attachments: list[EducationCostAttachment] | None = None) -> dict:
    allocated = sum((Decimal(item["amount"]) for item in allocations), Decimal("0"))
    ended_on = row.ended_on or row.occurred_on
    quantity_days = (ended_on - row.occurred_on).days + 1
    unit_price = row.unit_price
    if unit_price <= 0:
        unit_price = (row.amount / quantity_days).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return {
        "id": row.id,
        "occurred_on": row.occurred_on.isoformat(),
        "ended_on": ended_on.isoformat(),
        "category": row.category,
        "detail": row.detail,
        "unit_price": _money(unit_price),
        "quantity_days": quantity_days,
        "amount": _money(row.amount),
        "allocated_amount": _money(allocated),
        "unallocated_amount": _money(max(row.amount - allocated, Decimal("0"))),
        "vendor": row.vendor,
        "document_no": row.document_no,
        "source_ref": row.source_ref,
        "note": row.note,
        "version": row.version,
        "allocations": allocations,
        "attachments": [_attachment_data(item) for item in (attachments or [])],
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
            "special_achievement": bool(report.get("special_achievement", False)),
            "special_achievement_note": report.get("special_achievement_note", ""),
            "problem_flag": bool(report.get("problem_flag", False)),
            "problem_note": report.get("problem_note", ""),
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


def _monthly_summary_data(row: EducationMonthlySummary) -> dict:
    return {
        "id": row.id,
        "period_start": row.month.isoformat(),
        "summary": row.summary,
        "achievements": row.achievements,
        "problems": row.problems,
        "next_month_plan": row.next_month_plan,
        "version": row.version,
    }


def _safe_attachment_name(value: str | None) -> str:
    name = Path((value or "").replace("\\", "/")).name.strip()
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', "_", name).strip(" .")
    suffix = Path(name).suffix.lower()
    if not name:
        raise HTTPException(422, "附件文件名无效")
    if suffix not in ATTACHMENT_SUFFIXES:
        raise HTTPException(415, "凭证附件仅支持 PDF、图片、Word、Excel 和 ZIP")
    if len(name) > 180:
        name = f"{Path(name).stem[:150]}{suffix}"
    return name


def _attachment_root() -> Path:
    root = (settings.knowledge_root / ".jaos-ledger-files" / "education-costs").resolve()
    root.relative_to(settings.knowledge_root.resolve())
    return root


def _cost_for_cohort(db: Session, user: User, cohort_id: str, document_id: str, *, write: bool = False):
    cohort = _cohort(db, user, cohort_id, write=write)
    document = db.get(EducationCostDocument, document_id)
    if document is None or not document.active or document.entity_id != cohort.entity_id:
        raise HTTPException(404, "成本单据不存在")
    belongs = db.scalar(select(func.count(EducationCostAllocation.id)).where(
        EducationCostAllocation.cost_document_id == document.id,
        EducationCostAllocation.cohort_id == cohort.id,
    ))
    if not belongs:
        raise HTTPException(404, "成本单据不属于当前班期")
    return cohort, document


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


def _cost_pricing(payload: CostDocumentCreate | CostDocumentUpdate) -> tuple[int, Decimal]:
    ended_on = payload.ended_on or payload.occurred_on
    quantity_days = (ended_on - payload.occurred_on).days + 1
    total = (payload.unit_price * quantity_days).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return quantity_days, total


def _ledger_target(base_cohort, payload: CostDocumentCreate | CostDocumentUpdate) -> tuple[str, str | None, date, Decimal, str]:
    _, total = _cost_pricing(payload)
    return (base_cohort.id, None, _month(payload.occurred_on), total, payload.note)


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
    monthly_summaries = db.scalars(
        select(EducationMonthlySummary)
        .where(EducationMonthlySummary.cohort_id == cohort.id)
        .order_by(EducationMonthlySummary.month)
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
    attachments_by_document: dict[str, list[EducationCostAttachment]] = {}
    if grouped:
        for attachment in db.scalars(select(EducationCostAttachment).where(
            EducationCostAttachment.cost_document_id.in_(grouped.keys()),
        ).order_by(EducationCostAttachment.created_at, EducationCostAttachment.id)).all():
            attachments_by_document.setdefault(attachment.cost_document_id, []).append(attachment)

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

    costs = [_cost_data(document, allocations, attachments_by_document.get(document.id, [])) for document, allocations in grouped.values()]
    return {
        "schedule": {
            "generated": bool(days),
            "days": [_day_data(day, include_report=can_view_logs) for day in days],
            "monthly_summaries": [_monthly_summary_data(item) for item in monthly_summaries] if can_view_logs else [],
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
            "ledger_total": _money(sum((allocation.amount for allocation, _, _ in allocation_rows), Decimal("0"))),
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


@router.put("/cohorts/{cohort_id}/teaching-month-summaries/{period_start}")
def update_monthly_summary(cohort_id: str, period_start: str, payload: MonthlySummaryUpdate,
                           user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort = _cohort(db, user, cohort_id, write=True)
    try:
        month = date.fromisoformat(period_start)
    except ValueError:
        raise HTTPException(422, "教学月开始日期格式无效") from None
    teaching_month_starts = {
        cohort.start_date + timedelta(days=index * 29)
        for index in range(((cohort.end_date - cohort.start_date).days // 29) + 1)
    }
    if month not in teaching_month_starts:
        raise HTTPException(422, "教学月必须按开班日起每29天划分")
    row = db.scalar(select(EducationMonthlySummary).where(
        EducationMonthlySummary.cohort_id == cohort.id,
        EducationMonthlySummary.month == month,
    ).with_for_update())
    before = _monthly_summary_data(row) if row else None
    if row is None:
        if payload.version != 0:
            raise HTTPException(409, "教学月总结已更新，请刷新后重试")
        row = EducationMonthlySummary(
            cohort_id=cohort.id, month=month, updated_by_user_id=user.id, version=1,
        )
        db.add(row)
    else:
        if row.version != payload.version:
            raise HTTPException(409, "教学月总结已更新，请刷新后重试")
        row.version += 1
    row.summary = payload.summary
    row.achievements = payload.achievements
    row.problems = payload.problems
    row.next_month_plan = payload.next_month_plan
    row.updated_by_user_id = user.id
    _audit(db, user, "education_monthly_summary_updated", before, _monthly_summary_data(row))
    _commit(db)
    return {"id": row.id, "version": row.version}


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
    quantity_days, total = _cost_pricing(payload)
    target = _ledger_target(cohort, payload)
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
            and existing.unit_price == payload.unit_price
            and existing.amount == total
            and existing.vendor == payload.vendor
            and existing.document_no == payload.document_no
            and existing.source_ref == payload.source_ref
            and existing.note == payload.note
        )
        ledger_matches = len(existing_allocations) == 1 and (
            existing_allocations[0].cohort_id,
            existing_allocations[0].student_id,
            existing_allocations[0].allocation_month,
            existing_allocations[0].amount,
            existing_allocations[0].note,
        ) == target
        if not source_matches or not ledger_matches:
            raise HTTPException(409, "提交标识冲突，请刷新后重试")
        return {"id": existing.id}

    document = EducationCostDocument(
        id=str(payload.request_id), entity_id=cohort.entity_id, occurred_on=payload.occurred_on,
        ended_on=payload.ended_on or payload.occurred_on,
        category=payload.category, detail=payload.detail,
        unit_price=payload.unit_price, amount=total,
        vendor=payload.vendor, document_no=payload.document_no, source_ref=payload.source_ref,
        note=payload.note, created_by_user_id=user.id, version=1, active=True,
    )
    db.add(document)
    target_cohort_id, student_id, ledger_month, amount, note = target
    db.add(EducationCostAllocation(
        cost_document_id=document.id, cohort_id=target_cohort_id, student_id=student_id,
        allocation_month=ledger_month, amount=amount, note=note,
        created_by_user_id=user.id,
    ))
    _audit(db, user, "education_cost_document_created", None, {
        "id": document.id, "cohort_id": cohort.id, "category": document.category,
        "unit_price": _money(document.unit_price), "quantity_days": quantity_days,
        "amount": _money(document.amount), "ledger_mode": "direct",
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
    attachments = db.scalars(select(EducationCostAttachment).where(
        EducationCostAttachment.cost_document_id == document.id,
    ).order_by(EducationCostAttachment.created_at, EducationCostAttachment.id)).all()
    result = _cost_data(document, allocations, attachments)
    result.update({
        "ledger_mode": "direct",
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
    quantity_days, total = _cost_pricing(payload)
    target = _ledger_target(cohort, payload)
    before = {
        "id": document.id, "category": document.category, "detail": document.detail,
        "unit_price": _money(document.unit_price), "amount": _money(document.amount),
        "version": document.version,
        "allocation_count": db.scalar(select(func.count(EducationCostAllocation.id)).where(
            EducationCostAllocation.cost_document_id == document.id,
        )),
    }
    document.occurred_on = payload.occurred_on
    document.ended_on = payload.ended_on or payload.occurred_on
    document.category = payload.category
    document.detail = payload.detail
    document.unit_price = payload.unit_price
    document.amount = total
    document.vendor = payload.vendor
    document.document_no = payload.document_no
    document.source_ref = payload.source_ref
    document.note = payload.note
    document.version += 1
    db.execute(delete(EducationCostAllocation).where(EducationCostAllocation.cost_document_id == document.id))
    target_cohort_id, student_id, ledger_month, amount, note = target
    db.add(EducationCostAllocation(
        cost_document_id=document.id, cohort_id=target_cohort_id, student_id=student_id,
        allocation_month=ledger_month, amount=amount, note=note, created_by_user_id=user.id,
    ))
    _audit(db, user, "education_cost_document_updated", before, {
        "id": document.id, "category": document.category, "detail": document.detail,
        "unit_price": _money(document.unit_price), "quantity_days": quantity_days,
        "amount": _money(document.amount), "version": document.version,
        "ledger_mode": "direct",
    })
    _commit(db)
    return {"id": document.id}


@router.post("/cohorts/{cohort_id}/cost-documents/{document_id}/attachments")
async def upload_cost_attachment(cohort_id: str, document_id: str, file: UploadFile = File(...),
                                 user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cohort, document = _cost_for_cohort(db, user, cohort_id, document_id, write=True)
    filename = _safe_attachment_name(file.filename)
    attachment_id = secrets.token_hex(16)
    target_dir = (_attachment_root() / cohort.id / document.id).resolve()
    target_dir.relative_to(_attachment_root())
    temporary = target_dir / f".{attachment_id}.part"
    final_path = target_dir / f"{attachment_id}-{filename}"
    size = 0
    digest = hashlib.sha256()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with temporary.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > min(settings.inbox_max_file_bytes, ATTACHMENT_MAX_BYTES):
                    raise HTTPException(413, "单个凭证附件不能超过200MB")
                digest.update(chunk)
                destination.write(chunk)
        if size == 0:
            raise HTTPException(422, "不能上传空附件")
        temporary.replace(final_path)
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(503, "凭证附件暂时无法写入NAS") from exc
    row = EducationCostAttachment(
        id=attachment_id, cost_document_id=document.id, filename=filename,
        source_path=str(final_path), size_bytes=size, sha256=digest.hexdigest(),
        uploaded_by_user_id=user.id,
    )
    db.add(row)
    _audit(db, user, "education_cost_attachment_uploaded", None, {
        "id": row.id, "cost_document_id": document.id, "filename": filename,
        "size_bytes": size, "sha256": row.sha256,
    })
    try:
        _commit(db)
    except Exception:
        final_path.unlink(missing_ok=True)
        raise
    return _attachment_data(row)


@router.get("/cohorts/{cohort_id}/cost-documents/{document_id}/attachments/{attachment_id}")
def download_cost_attachment(cohort_id: str, document_id: str, attachment_id: str,
                             user: User = Depends(current_user), db: Session = Depends(get_db)):
    _cost_for_cohort(db, user, cohort_id, document_id)
    row = db.scalar(select(EducationCostAttachment).where(
        EducationCostAttachment.id == attachment_id,
        EducationCostAttachment.cost_document_id == document_id,
    ))
    if row is None:
        raise HTTPException(404, "凭证附件不存在")
    source = Path(row.source_path).resolve()
    try:
        source.relative_to(_attachment_root())
    except ValueError:
        raise HTTPException(409, "凭证附件路径异常") from None
    if not source.is_file():
        raise HTTPException(404, "凭证附件原文件不存在")
    return FileResponse(source, filename=row.filename)


@router.delete("/cohorts/{cohort_id}/cost-documents/{document_id}/attachments/{attachment_id}")
def delete_cost_attachment(cohort_id: str, document_id: str, attachment_id: str,
                           user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _cost_for_cohort(db, user, cohort_id, document_id, write=True)
    row = db.scalar(select(EducationCostAttachment).where(
        EducationCostAttachment.id == attachment_id,
        EducationCostAttachment.cost_document_id == document_id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "凭证附件不存在")
    source = Path(row.source_path).resolve()
    try:
        source.relative_to(_attachment_root())
    except ValueError:
        raise HTTPException(409, "凭证附件路径异常") from None
    before = _attachment_data(row)
    db.delete(row)
    _audit(db, user, "education_cost_attachment_deleted", before, {
        "id": row.id, "cost_document_id": document_id,
    })
    _commit(db)
    source.unlink(missing_ok=True)
    return {"deleted": True}
