from __future__ import annotations

import json
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .database import get_db
from .education_enrollment import _student
from .education_system import _audit, _commit, _require_access
from .education_catalog import PERIODS
from .models import EducationAssessment, EducationStaff, User

router = APIRouter(prefix="/v1/pm/education", tags=["education-assessments"])
STAGES = {"baseline": "前期评估（入学基线）", "phase": "阶段性观察总结", "final": "结营综合评估"}
DIMENSIONS = ("操作基础", "游戏理解", "团队协作", "学习执行", "生活自律")
TEXT_FIELDS = {
    "observations": "客观观察与证据", "strengths": "优势表现", "improvements": "待改善事项",
    "goals": "学习目标", "grouping": "分班 / 分组建议", "teaching_plan": "教学安排 / 纠偏措施",
    "stage_summary": "本阶段成长总结", "final_summary": "结营综合结论",
    "parent_feedback": "给家长的客观反馈", "parent_response": "家长意见记录",
    "conservative_outlook": "未来预期 · 保守情景", "optimistic_outlook": "未来预期 · 乐观情景",
    "outlook_basis": "预期依据、前提与不确定性", "next_steps": "后续建议",
}


class AssessmentFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    stage: Literal["baseline", "phase", "final"]
    assessed_on: date
    evaluator_staff_id: UUID
    stage_name: str = Field(min_length=1, max_length=120)
    scores: dict[str, int | None] = Field(default_factory=dict)
    observations: str = Field(min_length=1, max_length=3000)
    strengths: str = Field(default="", max_length=2000)
    improvements: str = Field(default="", max_length=2000)
    goals: str = Field(default="", max_length=2000)
    grouping: str = Field(default="", max_length=500)
    teaching_plan: str = Field(default="", max_length=2000)
    stage_summary: str = Field(default="", max_length=3000)
    final_summary: str = Field(default="", max_length=3000)
    parent_feedback: str = Field(default="", max_length=3000)
    parent_response: str = Field(default="", max_length=2000)
    conservative_outlook: str = Field(default="", max_length=2000)
    optimistic_outlook: str = Field(default="", max_length=2000)
    outlook_basis: str = Field(default="", max_length=2000)
    next_steps: str = Field(default="", max_length=2000)

    @field_validator("scores", mode="before")
    @classmethod
    def validate_scores(cls, value):
        if not isinstance(value, dict) or any(key not in DIMENSIONS or (score is not None and (type(score) is not int or not 1 <= score <= 5)) for key, score in value.items()):
            raise ValueError("评分仅支持规定维度的1至5分，未评估请留空")
        return value

    @model_validator(mode="after")
    def validate_outlook(self):
        if (self.conservative_outlook or self.optimistic_outlook) and not self.outlook_basis:
            raise ValueError("填写未来预期时必须说明依据、前提与不确定性")
        if self.stage == "final" and not self.final_summary:
            raise ValueError("结营评估须填写综合结论")
        return self


class AssessmentCreate(AssessmentFields):
    request_id: UUID


class AssessmentUpdate(AssessmentFields):
    version: int = Field(ge=1)


def _content(payload):
    return json.dumps(payload.model_dump(mode="json", exclude={"request_id", "version", "stage", "assessed_on", "evaluator_staff_id"}), ensure_ascii=False)


def _data(db, row):
    staff = db.get(EducationStaff, row.evaluator_staff_id)
    return {"id": row.id, "stage": row.stage, "assessed_on": row.assessed_on.isoformat(),
        "evaluator_staff_id": row.evaluator_staff_id, "evaluator_name": staff.name if staff else "历史教练",
        "version": row.version, **json.loads(row.content_json)}


def _check_staff(db, cohort_id, staff_id, previous=None):
    staff = db.get(EducationStaff, str(staff_id))
    if staff is None or staff.cohort_id != cohort_id:
        raise HTTPException(422, "请选择本班期的评估教师或助教")
    if not staff.active and (previous is None or previous.evaluator_staff_id != str(staff_id)):
        raise HTTPException(422, "该人员已移除，请选择在册教师或助教")


def _access(db, user, cohort_id, student_id, *, write=False):
    _require_access(user, write=True)  # Teaching records are not part of finance read access.
    return _student(db, user, cohort_id, student_id, write=write)


@router.get("/cohorts/{cohort_id}/students/{student_id}/assessments")
def list_assessments(cohort_id: str, student_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _access(db, user, cohort_id, student_id)
    rows = db.scalars(select(EducationAssessment).where(EducationAssessment.student_id == student_id)
        .order_by(EducationAssessment.assessed_on, EducationAssessment.created_at)).all()
    return {"items": [_data(db, row) for row in rows], "stages": STAGES, "dimensions": DIMENSIONS}


@router.post("/cohorts/{cohort_id}/students/{student_id}/assessments")
def create_assessment(cohort_id: str, student_id: str, payload: AssessmentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _access(db, user, cohort_id, student_id, write=True)
    _check_staff(db, cohort_id, payload.evaluator_staff_id)
    existing = db.get(EducationAssessment, str(payload.request_id))
    if existing:
        if existing.student_id != student_id or existing.stage != payload.stage or existing.assessed_on != payload.assessed_on or existing.evaluator_staff_id != str(payload.evaluator_staff_id) or existing.content_json != _content(payload):
            raise HTTPException(409, "提交记录已变化，请刷新确认")
        return {"id": existing.id}
    if payload.stage != "phase" and db.scalar(select(EducationAssessment.id).where(EducationAssessment.student_id == student_id, EducationAssessment.stage == payload.stage)):
        raise HTTPException(409, "该学员已有入学 / 结营评估，请修改原记录；阶段观察可多次追加")
    row = EducationAssessment(id=str(payload.request_id), student_id=student_id, stage=payload.stage,
        assessed_on=payload.assessed_on, evaluator_staff_id=str(payload.evaluator_staff_id), content_json=_content(payload), created_by_user_id=user.id, version=1)
    db.add(row)
    _audit(db, user, "education_assessment_created", None, {"assessment_id": row.id, "student_id": student_id, "stage": row.stage, "version": 1})
    _commit(db)
    return {"id": row.id}


@router.patch("/cohorts/{cohort_id}/students/{student_id}/assessments/{assessment_id}")
def update_assessment(cohort_id: str, student_id: str, assessment_id: str, payload: AssessmentUpdate,
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    _access(db, user, cohort_id, student_id, write=True)
    row = db.scalar(select(EducationAssessment).where(EducationAssessment.id == assessment_id, EducationAssessment.student_id == student_id))
    if row is None:
        raise HTTPException(404, "评估记录不存在")
    if row.version != payload.version or row.stage != payload.stage:
        raise HTTPException(409, "评估版本或类型已变化，请刷新后修改")
    _check_staff(db, cohort_id, payload.evaluator_staff_id, previous=row)
    row.assessed_on = payload.assessed_on
    row.evaluator_staff_id = str(payload.evaluator_staff_id)
    row.content_json = _content(payload)
    row.version += 1
    _audit(db, user, "education_assessment_updated", None, {"assessment_id": row.id, "student_id": student_id, "stage": row.stage, "version": row.version})
    _commit(db)
    return {"id": row.id}


@router.get("/cohorts/{cohort_id}/students/{student_id}/graduation-report")
def graduation_report(cohort_id: str, student_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    student = _access(db, user, cohort_id, student_id)
    rows = db.scalars(select(EducationAssessment).where(EducationAssessment.student_id == student_id)
        .order_by(EducationAssessment.assessed_on, EducationAssessment.created_at)).all()
    if not any(row.stage == "final" for row in rows):
        raise HTTPException(409, "请先保存结营综合评估，再生成结营报告")
    lines = ["星曜电竞 · 教培结营报告", f"学员：{student.name}", f"游戏项目：{student.game}",
        f"课程：{PERIODS[student.course_period]}，{student.study_start} 至 {student.study_end}",
        "本报告依据教练记录整理；未填写项目不代表已完成评估。未来预期为条件性判断，不承诺段位、升学或职业结果。"]
    for row in rows:
        item = _data(db, row)
        lines += ["", f"{STAGES[row.stage]} · {item['stage_name']}", f"日期：{row.assessed_on}　评估人：{item['evaluator_name']}"]
        lines += [f"{dimension}：{item['scores'].get(dimension) or '未评估'}" for dimension in DIMENSIONS]
        lines += [f"{label}：{item[key]}" for key, label in TEXT_FIELDS.items() if item.get(key)]
    # No ID number, telephone, accommodation or fee records in parent reports.
    return {"title": f"{student.name}-结营报告", "text": "\n".join(lines)}
