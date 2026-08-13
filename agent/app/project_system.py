from __future__ import annotations

import json
import re
import secrets
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_user
from .business_entities import (
    BUSINESS_ENTITY_BY_NAME,
    canonical_business_entity_name,
)
from .config import settings
from .database import get_db
from .models import (
    AuditLog,
    BusinessEntity,
    ManagedProject,
    ProjectCashflowPlan,
    ProjectDeletionRequest,
    ProjectProgressUpdate,
    ProjectReview,
    User,
)
from .retrieval import CONFIDENTIALITY_RANK


router = APIRouter(prefix="/v1/pm", tags=["project-management"])
EXECUTIVE_APPROVERS = {
    "founder": {"found", "founder"},
}
PROJECT_ATTACHMENT_SUFFIXES = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".png", ".jpg", ".jpeg", ".zip",
}
PROJECT_NO_RE = re.compile(r"^[A-Za-z0-9_-]{2,40}$")
CONTRACT_STATUS_LABELS = {
    "unsigned": "未签署",
    "signed_received": "已签署收件",
}
# A project is considered started only after initiation approval advances it
# into execution.  Review/rejected pipeline states intentionally do not warn.
# Closing and archived states remain post-start for historical correctness.
POST_START_PROJECT_STATUSES = {
    "active", "closing_review", "closing_rejected", "closed", "archived",
}


class ProjectUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    company_name: str = Field(min_length=1, max_length=240)
    client: str = Field(min_length=1, max_length=240)
    # Optional on PATCH for compatibility with an older Web client. When the
    # field is omitted, keep the stored contact; an explicit empty string
    # clears it.
    client_contact: str | None = Field(default=None, max_length=240)
    business_category: str = Field(min_length=1, max_length=120)
    members: list[str] = Field(min_length=1, max_length=50)
    planned_start: date
    planned_end: date
    objective: str = Field(min_length=4, max_length=5000)
    contract_document_id: str | None = Field(default=None, max_length=36)
    # Optional for compatibility with clients deployed before this field.
    # Omission preserves the stored value; an explicit value updates it.
    contract_status: Literal["unsigned", "signed_received"] | None = None
    contract_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    budget_revenue: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    budget_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)
    budget_tax: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=2)


class ProjectCashflowCreate(BaseModel):
    direction: str = Field(pattern="^(receivable|payable)$")
    due_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    counterparty: str | None = Field(default=None, max_length=240)
    note: str | None = Field(default=None, max_length=1000)


class ProjectContractStatusUpdate(BaseModel):
    contract_status: Literal["unsigned", "signed_received"]


class ProjectProcessFinanceUpdate(BaseModel):
    process_received: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    process_spent: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    process_advanced: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class ProjectCashflowActualUpdate(BaseModel):
    actual_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    actual_date: date | None = None


class ProjectProgressCreate(BaseModel):
    progress_percent: int = Field(ge=0, le=100)
    current_stage: str = Field(min_length=1, max_length=120)
    completed: str = Field(min_length=1, max_length=3000)
    next_step: str = Field(min_length=1, max_length=3000)
    risks: str | None = Field(default=None, max_length=3000)
    needs_coordination: bool = False


class ProjectReviewRequest(BaseModel):
    stage: str = Field(pattern="^(initiation|closing)$")
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=1000)


class ProjectDeletionCreate(BaseModel):
    reason: str = Field(min_length=2, max_length=1000)


class ProjectDeletionDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=1000)


class ProjectArchiveRequest(BaseModel):
    action: str = Field(pattern="^(archive|restore)$")


def _is_finance(user: User) -> bool:
    return bool(
        user.active
        and user.organization_role == "finance"
        and CONFIDENTIALITY_RANK.get(user.confidentiality_ceiling, 0) >= 4
    )


def _is_management(user: User) -> bool:
    return bool(
        user.active
        and user.organization_role == "management"
        and user.confidentiality_ceiling == "L5"
    )


def _can_access_project_management(user: User) -> bool:
    return bool(
        user.active
        and (
            user.organization_role == "business"
            or _is_finance(user)
            or _is_management(user)
        )
    )


def _reviewer_slot(user: User) -> str | None:
    username = user.username.casefold()
    if _is_management(user):
        for slot, usernames in EXECUTIVE_APPROVERS.items():
            if username in usernames:
                return slot
    return None


def _project_visible(user: User, project: ManagedProject) -> bool:
    if _is_finance(user) or _is_management(user):
        return True
    return bool(
        user.active
        and user.organization_role == "business"
        and (project.created_by_user_id == user.id or project.manager_user_id == user.id)
    )


def _project_editable(user: User, project: ManagedProject) -> bool:
    return bool(
        user.active
        and user.organization_role == "business"
        and project.manager_user_id == user.id
    )


def _safe_part(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value).strip(" .")
    return cleaned[:140] or fallback


def _normalize_project_no(value: str) -> str:
    """Normalize a Feishu project segment before it becomes a folder name.

    Project numbers are immutable after creation because the number is also
    the stable NAS attachment directory. Restricting the character set here
    prevents path traversal and keeps the value portable across fnOS/SMB.
    """

    normalized = unicodedata.normalize("NFKC", value).strip()
    if not PROJECT_NO_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=422,
            detail="项目编号须为 2–40 位，只能包含英文字母、数字、短横线和下划线",
        )
    return normalized


def _remove_attachment_after_failed_create(path: str | None) -> None:
    """Remove the just-uploaded file if a concurrent number claim wins."""

    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        # The database transaction is authoritative. A filesystem cleanup
        # failure must not hide the duplicate-number response from the PM.
        pass


def _member_identity(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _normalize_project_members(
    values: object,
    *,
    required: bool,
    manager_name: str | None = None,
) -> list[str]:
    """Validate, trim and de-duplicate the project's execution team."""

    if not isinstance(values, list) or len(values) > 50:
        raise HTTPException(status_code=422, detail="执行团队名单格式错误")
    members: list[str] = []
    seen: set[str] = set()
    manager_key = _member_identity(manager_name or "")
    for value in values:
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail="执行团队成员姓名格式错误")
        name = unicodedata.normalize("NFKC", value).strip()
        if not name:
            continue
        if len(name) > 80:
            raise HTTPException(status_code=422, detail="执行团队成员姓名不能超过80个字符")
        key = _member_identity(name)
        if key == manager_key or key in seen:
            continue
        seen.add(key)
        members.append(name)
    if required and not members:
        raise HTTPException(status_code=422, detail="请至少填写1名执行团队成员")
    return members


def _project_members(project: ManagedProject, manager_name: str | None = None) -> list[str]:
    """Read legacy projects defensively; old empty values remain readable."""

    try:
        values = json.loads(project.members_json or "[]")
        return _normalize_project_members(
            values, required=False, manager_name=manager_name
        )
    except (json.JSONDecodeError, TypeError, HTTPException):
        return []


def _entity(db: Session, name: str, user: User) -> BusinessEntity:
    normalized = canonical_business_entity_name(name)
    if normalized is None:
        raise HTTPException(
            status_code=422,
            detail="项目签约主体必须选择系统登记的三家公司之一",
        )
    entity = db.scalar(select(BusinessEntity).where(BusinessEntity.name == normalized))
    if entity is None:
        definition = BUSINESS_ENTITY_BY_NAME[normalized]
        entity = BusinessEntity(
            name=normalized,
            short_name=definition["display_name"],
            created_by_user_id=user.id,
        )
        db.add(entity)
        db.flush()
    elif not entity.active:
        entity.active = True
    return entity


async def _save_attachment(
    upload: UploadFile | None,
    project_no: str,
    folder: str,
) -> str | None:
    if upload is None or not upload.filename:
        return None
    filename = Path(upload.filename).name
    suffix = Path(filename).suffix.lower()
    if suffix not in PROJECT_ATTACHMENT_SUFFIXES:
        raise HTTPException(status_code=415, detail="项目附件格式不支持")
    payload = await upload.read(settings.inbox_max_file_bytes + 1)
    await upload.close()
    if len(payload) > settings.inbox_max_file_bytes:
        raise HTTPException(status_code=413, detail="附件超过大小限制")
    if not payload:
        raise HTTPException(status_code=422, detail="不能上传空附件")
    target = settings.knowledge_root / "项目管理" / project_no / folder
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{secrets.token_hex(3)}_{_safe_part(filename, '附件'+suffix)}"
    path.write_bytes(payload)
    return str(path)


def _review_status(db: Session, project: ManagedProject, stage: str) -> list[dict]:
    review_round = project.initiation_round if stage == "initiation" else project.closing_round
    reviews = db.scalars(
        select(ProjectReview).where(
            ProjectReview.project_id == project.id,
            ProjectReview.stage == stage,
            ProjectReview.review_round == review_round,
        )
    ).all()
    by_slot = {item.reviewer_slot: item for item in reviews}
    labels = {"founder": "叶靖波"}
    return [{
        "slot": slot,
        "label": labels[slot],
        "decision": by_slot[slot].decision if slot in by_slot else "pending",
        "note": by_slot[slot].note if slot in by_slot else None,
        "reviewer": (
            db.get(User, by_slot[slot].reviewer_user_id).display_name
            if slot in by_slot and db.get(User, by_slot[slot].reviewer_user_id)
            else None
        ),
        "decided_at": by_slot[slot].decided_at if slot in by_slot else None,
    } for slot in ("founder",)]


def _deletion_request_payload(db: Session, project: ManagedProject) -> dict | None:
    request = db.scalar(
        select(ProjectDeletionRequest)
        .where(ProjectDeletionRequest.project_id == project.id)
        .order_by(ProjectDeletionRequest.created_at.desc())
        .limit(1)
    )
    if request is None:
        return None
    requester = db.get(User, request.requested_by_user_id)
    decider = db.get(User, request.decided_by_user_id) if request.decided_by_user_id else None
    return {
        "id": request.id,
        "status": request.status,
        "reason": request.reason,
        "requester": requester.display_name if requester else "",
        "decision_note": request.decision_note,
        "decider": decider.display_name if decider else None,
        "created_at": request.created_at,
        "decided_at": request.decided_at,
    }


def _receivable_summary(
    project: ManagedProject,
    plans: list[ProjectCashflowPlan],
) -> dict:
    receivables = [item for item in plans if item.direction == "receivable"]
    planned = sum((item.amount for item in receivables), Decimal("0"))
    received = sum((item.actual_amount for item in receivables), Decimal("0"))
    if receivables:
        outstanding = max(planned - received, Decimal("0"))
    else:
        outstanding = max(project.actual_receivable or Decimal("0"), Decimal("0"))
    payment_complete = project.status in {"closed", "archived"} and outstanding <= 0
    if project.status == "archived":
        portfolio_group = "archived"
    elif project.status in {"active", "closing_review", "closing_rejected"}:
        portfolio_group = "ongoing"
    elif project.status == "closed" and outstanding > 0:
        portfolio_group = "closed_unpaid"
    elif project.status == "closed":
        portfolio_group = "ready_archive"
    else:
        portfolio_group = "pipeline"
    return {
        "planned_receivable": planned,
        "received_amount": received,
        "outstanding_receivable": outstanding,
        "payment_complete": payment_complete,
        "portfolio_group": portfolio_group,
    }


def _project_payload(db: Session, project: ManagedProject, detail: bool = False) -> dict:
    manager = db.get(User, project.manager_user_id)
    plans = db.scalars(
        select(ProjectCashflowPlan)
        .where(ProjectCashflowPlan.project_id == project.id)
        .order_by(ProjectCashflowPlan.due_date)
    ).all()
    contract_unsigned_alert = bool(
        project.status in POST_START_PROJECT_STATUSES
        and project.contract_status == "unsigned"
    )
    base = {
        "id": project.id,
        "project_no": project.project_no,
        "name": project.name,
        "company_name": project.company_name,
        "client": project.client,
        "client_contact": project.client_contact,
        "business_category": project.business_category,
        "manager": manager.display_name if manager else "",
        "manager_user_id": project.manager_user_id,
        "members": _project_members(
            project, manager.display_name if manager else None
        ),
        "planned_start": project.planned_start,
        "planned_end": project.planned_end,
        "objective": project.objective,
        "contract_document_id": project.contract_document_id,
        "contract_status": project.contract_status,
        "contract_status_label": CONTRACT_STATUS_LABELS[project.contract_status],
        "contract_alert": contract_unsigned_alert,
        "contract_unsigned_alert": contract_unsigned_alert,
        "contract_alert_message": (
            "项目已启动，合同仍未签署收件"
            if contract_unsigned_alert else None
        ),
        "contract_amount": project.contract_amount,
        "budget_revenue": project.budget_revenue,
        "budget_cost": project.budget_cost,
        "budget_tax": project.budget_tax,
        "expected_margin": project.budget_revenue - project.budget_cost - project.budget_tax,
        "process_received": project.process_received,
        "process_spent": project.process_spent,
        "process_advanced": project.process_advanced,
        "process_finance_updated_at": project.process_finance_updated_at,
        "status": project.status,
        "progress_percent": project.progress_percent,
        "current_stage": project.current_stage,
        "proposal_attached": bool(project.proposal_path),
        "closing_report_attached": bool(project.closing_report_path),
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        **_receivable_summary(project, plans),
    }
    if not detail:
        return base
    running = Decimal("0")
    lowest = Decimal("0")
    plan_rows = []
    for item in plans:
        running += item.amount if item.direction == "receivable" else -item.amount
        lowest = min(lowest, running)
        plan_rows.append({
            "id": item.id,
            "direction": item.direction,
            "due_date": item.due_date,
            "amount": item.amount,
            "counterparty": item.counterparty,
            "note": item.note,
            "actual_amount": item.actual_amount,
            "actual_date": item.actual_date,
            "running_cash": running,
        })
    updates = db.scalars(
        select(ProjectProgressUpdate)
        .where(ProjectProgressUpdate.project_id == project.id)
        .order_by(ProjectProgressUpdate.created_at.desc())
    ).all()
    base.update({
        "cashflow_plans": plan_rows,
        "maximum_funding_gap": abs(lowest),
        "progress_updates": [{
            "id": item.id,
            "progress_percent": item.progress_percent,
            "current_stage": item.current_stage,
            "completed": item.completed,
            "next_step": item.next_step,
            "risks": item.risks,
            "needs_coordination": item.needs_coordination,
            "creator": db.get(User, item.created_by_user_id).display_name,
            "created_at": item.created_at,
        } for item in updates],
        "initiation_reviews": _review_status(db, project, "initiation"),
        "closing_reviews": _review_status(db, project, "closing"),
        "closing_summary": project.closing_summary,
        "actual_revenue": project.actual_revenue,
        "actual_cost": project.actual_cost,
        "actual_receivable": project.actual_receivable,
        "actual_payable": project.actual_payable,
        "deletion_request": _deletion_request_payload(db, project),
    })
    return base


def _project_or_404(db: Session, user: User, project_id: str) -> ManagedProject:
    project = db.get(ManagedProject, project_id)
    if project is None or project.status == "deleted" or not _project_visible(user, project):
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("/projects")
def list_managed_projects(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not _can_access_project_management(user):
        raise HTTPException(status_code=403, detail="无权访问项目管理系统")
    projects = db.scalars(
        select(ManagedProject).order_by(ManagedProject.updated_at.desc())
    ).all()
    visible = [
        item for item in projects
        if item.status != "deleted" and _project_visible(user, item)
    ]
    counts = {status: sum(item.status == status for item in visible) for status in (
        "draft", "initiation_review", "active", "closing_review", "closed",
        "initiation_rejected", "closing_rejected", "archived",
    )}
    items = [_project_payload(db, item) for item in visible]
    priority = {
        "ongoing": 0,
        "closed_unpaid": 1,
        "pipeline": 2,
        "ready_archive": 3,
        "archived": 4,
    }
    items.sort(key=lambda item: (
        priority.get(item["portfolio_group"], 9),
        -item["updated_at"].timestamp(),
    ))
    portfolio_counts = {
        group: sum(item["portfolio_group"] == group for item in items)
        for group in priority
    }
    return {"counts": counts, "portfolio_counts": portfolio_counts, "items": items}


@router.post("/projects")
async def create_managed_project(
    project_no: str = Form(...),
    name: str = Form(...),
    company_name: str = Form(...),
    client: str = Form(...),
    client_contact: str = Form(default="", max_length=240),
    business_category: str = Form(...),
    planned_start: date = Form(...),
    planned_end: date = Form(...),
    objective: str = Form(...),
    members_json: str = Form(default="[]"),
    contract_document_id: str = Form(default=""),
    contract_status: Literal["unsigned", "signed_received"] = Form(default="unsigned"),
    contract_amount: Decimal = Form(default=Decimal("0")),
    budget_revenue: Decimal = Form(default=Decimal("0")),
    budget_cost: Decimal = Form(default=Decimal("0")),
    budget_tax: Decimal = Form(default=Decimal("0")),
    proposal_file: UploadFile | None = File(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not user.active or user.organization_role != "business":
        raise HTTPException(status_code=403, detail="仅业务角色可以发起项目")
    if planned_end < planned_start:
        raise HTTPException(status_code=422, detail="计划结束日期不能早于开始日期")
    try:
        members = json.loads(members_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="执行团队名单格式错误") from exc
    members = _normalize_project_members(
        members, required=True, manager_name=user.display_name
    )
    project_no = _normalize_project_no(project_no)
    if db.scalar(
        select(ManagedProject.id).where(ManagedProject.project_no == project_no)
    ):
        raise HTTPException(status_code=409, detail="项目编号已存在，请核对飞书项目段")
    proposal_path = await _save_attachment(proposal_file, project_no, "立项资料")
    entity = _entity(db, company_name, user)
    project = ManagedProject(
        project_no=project_no,
        name=name.strip(),
        entity_id=entity.id,
        company_name=entity.name,
        client=client.strip(),
        client_contact=client_contact.strip(),
        business_category=business_category.strip(),
        manager_user_id=user.id,
        members_json=json.dumps(members, ensure_ascii=False),
        planned_start=planned_start,
        planned_end=planned_end,
        objective=objective.strip(),
        proposal_path=proposal_path,
        contract_document_id=contract_document_id.strip() or None,
        contract_status=contract_status,
        contract_amount=max(contract_amount, Decimal("0")),
        budget_revenue=max(budget_revenue, Decimal("0")),
        budget_cost=max(budget_cost, Decimal("0")),
        budget_tax=max(budget_tax, Decimal("0")),
        created_by_user_id=user.id,
    )
    db.add(project)
    try:
        db.flush()
    except IntegrityError as exc:
        # The pre-check gives the usual fast path; the unique constraint is
        # still the final concurrency guard when two PMs submit together.
        db.rollback()
        _remove_attachment_after_failed_create(proposal_path)
        raise HTTPException(
            status_code=409,
            detail="项目编号已存在，请核对飞书项目段",
        ) from exc
    db.add(AuditLog(
        user_id=user.id,
        action="pm_project_create",
        details_json=json.dumps({"project_id": project.id, "project_no": project_no}, ensure_ascii=False),
    ))
    db.commit()
    return _project_payload(db, project, detail=True)


@router.get("/projects/{project_id}")
def get_managed_project(
    project_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    return _project_payload(db, _project_or_404(db, user, project_id), detail=True)


@router.patch("/projects/{project_id}")
def update_managed_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = _project_or_404(db, user, project_id)
    if not _project_editable(user, project) or project.status not in {
        "draft", "initiation_rejected", "active", "closing_rejected",
    }:
        raise HTTPException(status_code=409, detail="复核中或已结案的项目不能修改")
    if payload.planned_end < payload.planned_start:
        raise HTTPException(status_code=422, detail="计划结束日期不能早于开始日期")
    entity = _entity(db, payload.company_name, user)
    project.name = payload.name.strip()
    project.entity_id = entity.id
    project.company_name = entity.name
    project.client = payload.client.strip()
    if payload.client_contact is not None:
        project.client_contact = payload.client_contact.strip()
    project.business_category = payload.business_category.strip()
    project.members_json = json.dumps(
        _normalize_project_members(
            payload.members, required=True, manager_name=user.display_name
        ),
        ensure_ascii=False,
    )
    project.planned_start = payload.planned_start
    project.planned_end = payload.planned_end
    project.objective = payload.objective.strip()
    project.contract_document_id = payload.contract_document_id
    if payload.contract_status is not None:
        project.contract_status = payload.contract_status
    project.contract_amount = payload.contract_amount
    project.budget_revenue = payload.budget_revenue
    project.budget_cost = payload.budget_cost
    project.budget_tax = payload.budget_tax
    db.add(AuditLog(
        user_id=user.id,
        action="pm_project_update",
        details_json=json.dumps({"project_id": project.id}, ensure_ascii=False),
    ))
    db.commit()
    return _project_payload(db, project, detail=True)


@router.patch("/projects/{project_id}/contract-status")
def update_project_contract_status(
    project_id: str,
    payload: ProjectContractStatusUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Let the project owner correct contract receipt state at any stage.

    This deliberately avoids reopening all project fields after closing or
    archival.  The project manager can still clear a stale contract warning,
    while every change remains attributable in the audit log.
    """

    project = _project_or_404(db, user, project_id)
    if not _project_editable(user, project):
        raise HTTPException(status_code=403, detail="仅项目经理可以更新合同状态")
    previous_status = project.contract_status
    project.contract_status = payload.contract_status
    db.add(AuditLog(
        user_id=user.id,
        action="pm_contract_status_update",
        details_json=json.dumps({
            "project_id": project.id,
            "previous_status": previous_status,
            "contract_status": project.contract_status,
        }, ensure_ascii=False),
    ))
    db.commit()
    return _project_payload(db, project, detail=True)


@router.patch("/projects/{project_id}/process-finance")
def update_project_process_finance(
    project_id: str,
    payload: ProjectProcessFinanceUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Record PM-reported cumulative project cash figures during execution."""

    project = _project_or_404(db, user, project_id)
    if not _project_editable(user, project):
        raise HTTPException(status_code=403, detail="仅项目经理可以填报项目过程资金")
    if project.status not in {"active", "closing_rejected"}:
        raise HTTPException(status_code=409, detail="仅执行中的项目可以填报过程资金")
    previous = {
        "process_received": str(project.process_received),
        "process_spent": str(project.process_spent),
        "process_advanced": str(project.process_advanced),
    }
    project.process_received = payload.process_received
    project.process_spent = payload.process_spent
    project.process_advanced = payload.process_advanced
    project.process_finance_updated_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=user.id,
        action="pm_process_finance_update",
        details_json=json.dumps({
            "project_id": project.id,
            "previous": previous,
            "current": {
                "process_received": str(project.process_received),
                "process_spent": str(project.process_spent),
                "process_advanced": str(project.process_advanced),
            },
        }, ensure_ascii=False),
    ))
    db.commit()
    return _project_payload(db, project, detail=True)


@router.post("/projects/{project_id}/cashflow")
def add_project_cashflow(
    project_id: str,
    payload: ProjectCashflowCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = _project_or_404(db, user, project_id)
    if not _project_editable(user, project) or project.status not in {
        "draft", "initiation_rejected", "active", "closing_rejected",
    }:
        raise HTTPException(status_code=409, detail="当前状态不能新增收付款计划")
    item = ProjectCashflowPlan(
        project_id=project.id,
        direction=payload.direction,
        due_date=payload.due_date,
        amount=payload.amount,
        counterparty=payload.counterparty,
        note=payload.note,
        created_by_user_id=user.id,
    )
    db.add(item)
    db.add(AuditLog(
        user_id=user.id,
        action="pm_cashflow_plan_create",
        details_json=json.dumps({"project_id": project.id, "direction": item.direction, "amount": str(item.amount)}, ensure_ascii=False),
    ))
    db.commit()
    return {"id": item.id, "status": "created"}


@router.patch("/cashflow/{cashflow_id}/actual")
def update_project_cashflow_actual(
    cashflow_id: str,
    payload: ProjectCashflowActualUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not _is_finance(user):
        raise HTTPException(status_code=403, detail="仅财务可以确认实际收付款")
    item = db.get(ProjectCashflowPlan, cashflow_id)
    if item is None:
        raise HTTPException(status_code=404, detail="收付款计划不存在")
    item.actual_amount = payload.actual_amount
    item.actual_date = payload.actual_date
    db.add(AuditLog(
        user_id=user.id,
        action="pm_cashflow_actual_update",
        details_json=json.dumps({"cashflow_id": item.id, "actual_amount": str(item.actual_amount)}, ensure_ascii=False),
    ))
    db.commit()
    return {"id": item.id, "status": "updated"}


@router.post("/projects/{project_id}/submit-initiation")
def submit_project_initiation(
    project_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = _project_or_404(db, user, project_id)
    if not _project_editable(user, project) or project.status not in {"draft", "initiation_rejected"}:
        raise HTTPException(status_code=409, detail="当前状态不能提交立项")
    project.initiation_round += 1
    project.status = "initiation_review"
    project.submitted_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=user.id,
        action="pm_initiation_submit",
        details_json=json.dumps({"project_id": project.id, "round": project.initiation_round}, ensure_ascii=False),
    ))
    db.commit()
    return _project_payload(db, project, detail=True)


@router.post("/projects/{project_id}/progress")
def create_progress_update(
    project_id: str,
    payload: ProjectProgressCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = _project_or_404(db, user, project_id)
    if not _project_editable(user, project) or project.status != "active":
        raise HTTPException(status_code=409, detail="仅执行中的项目可以更新进度")
    update = ProjectProgressUpdate(
        project_id=project.id,
        progress_percent=payload.progress_percent,
        current_stage=payload.current_stage,
        completed=payload.completed,
        next_step=payload.next_step,
        risks=payload.risks,
        needs_coordination=payload.needs_coordination,
        created_by_user_id=user.id,
    )
    db.add(update)
    project.progress_percent = payload.progress_percent
    project.current_stage = payload.current_stage
    db.add(AuditLog(
        user_id=user.id,
        action="pm_progress_create",
        details_json=json.dumps({"project_id": project.id, "progress": payload.progress_percent}, ensure_ascii=False),
    ))
    db.commit()
    return {"id": update.id, "status": "created"}


@router.post("/projects/{project_id}/submit-closing")
async def submit_project_closing(
    project_id: str,
    closing_summary: str = Form(...),
    actual_revenue: Decimal = Form(...),
    actual_cost: Decimal = Form(...),
    actual_receivable: Decimal = Form(default=Decimal("0")),
    actual_payable: Decimal = Form(default=Decimal("0")),
    closing_file: UploadFile | None = File(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = _project_or_404(db, user, project_id)
    if not _project_editable(user, project) or project.status not in {"active", "closing_rejected"}:
        raise HTTPException(status_code=409, detail="当前状态不能提交结案")
    project.closing_report_path = (
        await _save_attachment(closing_file, project.project_no, "结案资料")
        or project.closing_report_path
    )
    project.closing_summary = closing_summary.strip()
    project.actual_revenue = max(actual_revenue, Decimal("0"))
    project.actual_cost = max(actual_cost, Decimal("0"))
    project.actual_receivable = max(actual_receivable, Decimal("0"))
    project.actual_payable = max(actual_payable, Decimal("0"))
    project.closing_round += 1
    project.status = "closing_review"
    project.closing_submitted_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=user.id,
        action="pm_closing_submit",
        details_json=json.dumps({"project_id": project.id, "round": project.closing_round}, ensure_ascii=False),
    ))
    db.commit()
    return _project_payload(db, project, detail=True)


@router.post("/projects/{project_id}/review")
def review_project(
    project_id: str,
    payload: ProjectReviewRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = _project_or_404(db, user, project_id)
    slot = _reviewer_slot(user)
    if slot is None:
        raise HTTPException(status_code=403, detail="当前账号不是本项目规定复核人")
    expected_status = "initiation_review" if payload.stage == "initiation" else "closing_review"
    if project.status != expected_status:
        raise HTTPException(status_code=409, detail="项目当前不在该复核阶段")
    review_round = project.initiation_round if payload.stage == "initiation" else project.closing_round
    existing = db.scalar(select(ProjectReview).where(
        ProjectReview.project_id == project.id,
        ProjectReview.stage == payload.stage,
        ProjectReview.review_round == review_round,
        ProjectReview.reviewer_slot == slot,
    ))
    if existing:
        raise HTTPException(status_code=409, detail="当前轮次已经完成复核")
    review = ProjectReview(
        project_id=project.id,
        stage=payload.stage,
        review_round=review_round,
        reviewer_slot=slot,
        reviewer_user_id=user.id,
        decision=payload.decision,
        note=payload.note,
    )
    db.add(review)
    db.flush()
    if payload.decision == "rejected":
        project.status = "initiation_rejected" if payload.stage == "initiation" else "closing_rejected"
    else:
        decisions = db.scalars(select(ProjectReview).where(
            ProjectReview.project_id == project.id,
            ProjectReview.stage == payload.stage,
            ProjectReview.review_round == review_round,
        )).all()
        approved = {item.reviewer_slot for item in decisions if item.decision == "approved"}
        # Legacy projects can still have finance/anliyuan approvals from the
        # earlier three-party workflow.  The testing-stage policy now only
        # requires the founder, so extra historical approvals must not keep a
        # project stuck in review.
        if "founder" in approved:
            if payload.stage == "initiation":
                project.status = "active"
                project.current_stage = "执行中"
            else:
                project.status = "closed"
                project.progress_percent = 100
                project.current_stage = "已结案"
    db.add(AuditLog(
        user_id=user.id,
        action=f"pm_{payload.stage}_review",
        details_json=json.dumps({
            "project_id": project.id,
            "slot": slot,
            "decision": payload.decision,
            "round": review_round,
        }, ensure_ascii=False),
    ))
    db.commit()
    return _project_payload(db, project, detail=True)


@router.post("/projects/{project_id}/deletion-request")
def request_project_deletion(
    project_id: str,
    payload: ProjectDeletionCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = _project_or_404(db, user, project_id)
    if not _project_editable(user, project):
        raise HTTPException(status_code=403, detail="只有项目经理可以申请删除自己的项目")
    existing = db.scalar(
        select(ProjectDeletionRequest).where(
            ProjectDeletionRequest.project_id == project.id,
            ProjectDeletionRequest.status == "pending",
        )
    )
    if existing:
        return {"status": "pending", "request_id": existing.id}
    request = ProjectDeletionRequest(
        project_id=project.id,
        requested_by_user_id=user.id,
        reason=payload.reason.strip(),
    )
    db.add(request)
    db.flush()
    db.add(AuditLog(
        user_id=user.id,
        action="pm_project_deletion_request",
        details_json=json.dumps({
            "project_id": project.id,
            "request_id": request.id,
            "reason": request.reason,
        }, ensure_ascii=False),
    ))
    db.commit()
    return {"status": "pending", "request_id": request.id}


@router.post("/deletion-requests/{request_id}/decide")
def decide_project_deletion(
    request_id: str,
    payload: ProjectDeletionDecision,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if _reviewer_slot(user) != "founder":
        raise HTTPException(status_code=403, detail="仅叶靖波可以复核项目删除申请")
    request = db.get(ProjectDeletionRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="删除申请不存在")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="该删除申请已经处理")
    project = db.get(ManagedProject, request.project_id)
    if project is None or project.status == "deleted":
        raise HTTPException(status_code=404, detail="项目不存在")
    request.status = payload.decision
    request.decision_note = payload.note.strip() if payload.note else None
    request.decided_by_user_id = user.id
    request.decided_at = datetime.now(timezone.utc)
    if payload.decision == "approved":
        project.status = "deleted"
    db.add(AuditLog(
        user_id=user.id,
        action="pm_project_deletion_decide",
        details_json=json.dumps({
            "project_id": project.id,
            "request_id": request.id,
            "decision": payload.decision,
            "note": request.decision_note,
        }, ensure_ascii=False),
    ))
    db.commit()
    return {
        "status": request.status,
        "request_id": request.id,
        "project_id": project.id,
        "project_deleted": project.status == "deleted",
    }


@router.post("/projects/{project_id}/archive")
def archive_managed_project(
    project_id: str,
    payload: ProjectArchiveRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not (_is_finance(user) or _is_management(user)):
        raise HTTPException(status_code=403, detail="仅最高管理者或财务可以归档项目")
    project = _project_or_404(db, user, project_id)
    plans = db.scalars(
        select(ProjectCashflowPlan).where(ProjectCashflowPlan.project_id == project.id)
    ).all()
    payment = _receivable_summary(project, plans)
    if payload.action == "archive":
        if project.status != "closed":
            raise HTTPException(status_code=409, detail="仅已结案项目可以归档")
        if not payment["payment_complete"]:
            raise HTTPException(status_code=409, detail="项目仍有待回款，不能归档")
        project.status = "archived"
        project.current_stage = "已归档"
    else:
        if project.status != "archived":
            raise HTTPException(status_code=409, detail="该项目尚未归档")
        project.status = "closed"
        project.current_stage = "已结案"
    db.add(AuditLog(
        user_id=user.id,
        action=f"pm_project_{payload.action}",
        details_json=json.dumps({"project_id": project.id}, ensure_ascii=False),
    ))
    db.commit()
    return _project_payload(db, project, detail=True)
