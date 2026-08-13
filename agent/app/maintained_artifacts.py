from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .evolution import (
    ARTIFACT_LABELS,
    FINAL_REQUIRED_ROLES,
    create_evolution_digest,
)
from .models import (
    AuditLog,
    Document,
    EvolutionCandidateRecord,
    EvolutionChangePlan,
    EvolutionReviewRun,
    MaintainedArtifact,
    Project,
    SourceHealth,
    User,
)
from .retrieval import CONFIDENTIALITY_RANK, is_authorized
from .source_integrity import source_is_available


ALLOWED_ARTIFACT_TYPES = frozenset(ARTIFACT_LABELS)
ARTIFACT_SOURCE_ROLES = {
    "company_profile": {"company_profile"},
    "capability_deck": {"company_profile"},
    "case_library": {"company_profile"},
    "team_profile": {"company_profile"},
}
ACTIVE_RUN_STATUSES = {"open", "plan_ready"}
REVIEWABLE_SCORE_BANDS = {"material", "review"}


class EvolutionWorkflowError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _fail(status_code: int, detail: str) -> None:
    raise EvolutionWorkflowError(status_code, detail)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _loads(raw: str, fallback):
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _effective_date(document: Document) -> date:
    return (document.valid_from or document.ingested_at).date()


def _highest_confidentiality(*levels: str) -> str:
    return max(
        levels,
        key=lambda level: CONFIDENTIALITY_RANK.get(level, 99),
    )


def _can_view(user: User, confidentiality: str) -> bool:
    return CONFIDENTIALITY_RANK.get(
        user.confidentiality_ceiling,
        0,
    ) >= CONFIDENTIALITY_RANK.get(confidentiality, 99)


def _audit(
    db: Session,
    *,
    user_id: str | None,
    action: str,
    document_ids: list[str] | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            document_ids_json=json.dumps(sorted(document_ids or [])),
            details_json=json.dumps(
                details or {},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    )


def _require_workflow_role(user: User) -> None:
    if user.role not in {"founder", "knowledge_admin"}:
        _fail(403, "无权管理知识进化复核")


def _require_founder(user: User) -> None:
    if user.role != "founder":
        _fail(403, "仅创始人可执行该知识进化决策")


def _baseline_validation_reason(
    db: Session,
    *,
    document: Document | None,
    artifact_type: str,
) -> str | None:
    if document is None:
        return "维护资料基线文档不存在"
    project = document.project
    if document.role not in ARTIFACT_SOURCE_ROLES[artifact_type]:
        return "维护资料基线必须登记为公司介绍类定稿"
    if document.knowledge_status != "current" or document.valid_to is not None:
        return "维护资料基线必须已经正式发布为当前版本"
    if project.knowledge_status != "current" or not project.confirmed:
        return "维护资料所属项目必须已确认并处于当前状态"
    if not document.is_final:
        return "维护资料基线必须是已确认定稿"
    if not any(chunk.text.strip() for chunk in document.chunks):
        return "维护资料基线缺少可引用正文"
    health = db.get(SourceHealth, document.content_hash)
    if not source_is_available(document.file_blob, health):
        return "维护资料基线原件不可用或完整性校验失败"
    return None


def _validate_baseline(
    db: Session,
    *,
    document_id: str,
    artifact_type: str,
    user: User,
) -> Document:
    if artifact_type not in ALLOWED_ARTIFACT_TYPES:
        _fail(422, "不支持的维护资料类型")
    document = db.get(Document, document_id)
    reason = _baseline_validation_reason(
        db,
        document=document,
        artifact_type=artifact_type,
    )
    if reason:
        _fail(409 if document else 404, reason)
    assert document is not None
    if not is_authorized(user, document, document.project):
        _fail(403, "无权使用该文档作为维护资料基线")
    return document


def _artifact_or_error(
    db: Session,
    *,
    artifact_id: str,
    user: User,
) -> MaintainedArtifact:
    _require_workflow_role(user)
    artifact = db.get(MaintainedArtifact, artifact_id)
    if artifact is None or artifact.status != "active":
        _fail(404, "维护资料不存在")
    if not _can_view(user, artifact.confidentiality):
        _fail(404, "维护资料不存在")
    return artifact


def _run_or_error(
    db: Session,
    *,
    run_id: str,
    user: User,
) -> EvolutionReviewRun:
    _require_workflow_role(user)
    run = db.get(EvolutionReviewRun, run_id)
    if run is None or not _can_view(user, run.confidentiality):
        _fail(404, "知识进化复核批次不存在")
    artifact = db.get(MaintainedArtifact, run.artifact_id)
    if artifact is None or not _can_view(user, artifact.confidentiality):
        _fail(404, "知识进化复核批次不存在")
    return run


def artifact_payload(db: Session, artifact: MaintainedArtifact) -> dict:
    document = db.get(Document, artifact.current_document_id)
    owner = db.get(User, artifact.owner_user_id)
    return {
        "id": artifact.id,
        "name": artifact.name,
        "artifact_type": artifact.artifact_type,
        "artifact_type_label": ARTIFACT_LABELS.get(
            artifact.artifact_type,
            artifact.artifact_type,
        ),
        "current_document": {
            "id": document.id,
            "title": document.title,
            "version": document.version,
            "effective_at": _effective_date(document),
        }
        if document
        else None,
        "owner": {
            "id": owner.id,
            "display_name": owner.display_name,
        }
        if owner
        else None,
        "audience": artifact.audience,
        "confidentiality": artifact.confidentiality,
        "cutoff_date": artifact.cutoff_date,
        "review_cadence_days": artifact.review_cadence_days,
        "next_review_at": artifact.next_review_at,
        "last_reviewed_at": artifact.last_reviewed_at,
        "section_map": _loads(artifact.section_map_json, {}),
        "status": artifact.status,
        "automatic_publication": False,
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }


def list_artifacts(db: Session, *, user: User) -> list[dict]:
    _require_workflow_role(user)
    rows = db.scalars(
        select(MaintainedArtifact).order_by(
            MaintainedArtifact.next_review_at.asc(),
            MaintainedArtifact.name.asc(),
        )
    ).all()
    return [
        artifact_payload(db, row)
        for row in rows
        if row.status == "active" and _can_view(user, row.confidentiality)
    ]


def list_baseline_documents(
    db: Session,
    *,
    user: User,
    artifact_type: str,
) -> list[dict]:
    _require_workflow_role(user)
    if artifact_type not in ALLOWED_ARTIFACT_TYPES:
        _fail(422, "不支持的维护资料类型")
    rows = db.scalars(
        select(Document)
        .join(Document.project)
        .where(
            Document.role.in_(ARTIFACT_SOURCE_ROLES[artifact_type]),
            Document.knowledge_status == "current",
            Document.valid_to.is_(None),
            Document.is_final.is_(True),
            Project.knowledge_status == "current",
            Project.confirmed.is_(True),
        )
        .order_by(Document.valid_from.desc(), Document.ingested_at.desc())
    ).all()
    response: list[dict] = []
    for document in rows:
        if not is_authorized(user, document, document.project):
            continue
        if _baseline_validation_reason(
            db,
            document=document,
            artifact_type=artifact_type,
        ):
            continue
        response.append(
            {
                "id": document.id,
                "title": document.title,
                "version": document.version,
                "effective_at": _effective_date(document),
                "project": document.project.name,
                "confidentiality": _highest_confidentiality(
                    document.confidentiality,
                    document.project.confidentiality,
                ),
                "supersedes_document_id": document.supersedes_document_id,
                "source_available": True,
            }
        )
    return response


def get_artifact(
    db: Session,
    *,
    artifact_id: str,
    user: User,
) -> dict:
    artifact = _artifact_or_error(db, artifact_id=artifact_id, user=user)
    runs = db.scalars(
        select(EvolutionReviewRun)
        .where(EvolutionReviewRun.artifact_id == artifact.id)
        .order_by(EvolutionReviewRun.reviewed_through.desc())
        .limit(20)
    ).all()
    return {
        **artifact_payload(db, artifact),
        "runs": [
            run_summary_payload(db, row)
            for row in runs
            if _can_view(user, row.confidentiality)
        ],
    }


def create_artifact(
    db: Session,
    *,
    user: User,
    name: str,
    artifact_type: str,
    current_document_id: str,
    audience: str,
    cutoff_date: date | None,
    review_cadence_days: int,
    section_map: dict[str, str],
) -> dict:
    _require_founder(user)
    if db.scalar(
        select(MaintainedArtifact).where(MaintainedArtifact.name == name)
    ):
        _fail(409, "同名维护资料已经存在")
    document = _validate_baseline(
        db,
        document_id=current_document_id,
        artifact_type=artifact_type,
        user=user,
    )
    effective_at = _effective_date(document)
    resolved_cutoff = cutoff_date or effective_at
    if resolved_cutoff < effective_at:
        _fail(422, "资料截止日不能早于当前基线文档生效日")
    if resolved_cutoff > _today():
        _fail(422, "资料截止日不能晚于今天")
    confidentiality = _highest_confidentiality(
        document.confidentiality,
        document.project.confidentiality,
    )
    artifact = MaintainedArtifact(
        name=name.strip(),
        artifact_type=artifact_type,
        current_document_id=document.id,
        owner_user_id=user.id,
        audience=audience,
        confidentiality=confidentiality,
        cutoff_date=resolved_cutoff,
        review_cadence_days=review_cadence_days,
        next_review_at=resolved_cutoff + timedelta(days=review_cadence_days),
        section_map_json=json.dumps(
            section_map,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    db.add(artifact)
    db.flush()
    _audit(
        db,
        user_id=user.id,
        action="maintained_artifact_registered",
        document_ids=[document.id],
        details={
            "artifact_id": artifact.id,
            "artifact_type": artifact_type,
            "audience": audience,
            "confidentiality": confidentiality,
            "cutoff_date": resolved_cutoff.isoformat(),
            "review_cadence_days": review_cadence_days,
        },
    )
    db.commit()
    db.refresh(artifact)
    return artifact_payload(db, artifact)


def _candidate_record_payload(row: EvolutionCandidateRecord) -> dict:
    payload = _loads(row.payload_json, {})
    return {
        **payload,
        "id": row.id,
        "run_id": row.run_id,
        "candidate_key": row.candidate_key,
        "review_status": row.review_status,
        "disclosure_status": row.disclosure_status,
        "decision_note": row.decision_note,
        "decided_at": row.decided_at,
        "created_at": row.created_at,
    }


def _change_plan_payload(plan: EvolutionChangePlan | None) -> dict | None:
    if plan is None:
        return None
    return {
        "id": plan.id,
        "run_id": plan.run_id,
        "artifact_id": plan.artifact_id,
        "status": plan.status,
        "version": plan.version,
        "source_fingerprint": plan.source_fingerprint,
        "plan": _loads(plan.plan_json, {}),
        "automatic_publication": False,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


def run_summary_payload(db: Session, run: EvolutionReviewRun) -> dict:
    summary = _loads(run.summary_json, {})
    plan = db.scalar(
        select(EvolutionChangePlan).where(EvolutionChangePlan.run_id == run.id)
    )
    return {
        "id": run.id,
        "artifact_id": run.artifact_id,
        "cutoff_date": run.cutoff_date,
        "reviewed_through": run.reviewed_through,
        "confidentiality": run.confidentiality,
        "status": run.status,
        "generation_mode": run.generation_mode,
        "summary": summary,
        "change_plan": _change_plan_payload(plan),
        "automatic_publication": False,
        "reviewed_at": run.reviewed_at,
        "created_at": run.created_at,
    }


def get_review_run(
    db: Session,
    *,
    run_id: str,
    user: User,
) -> dict:
    run = _run_or_error(db, run_id=run_id, user=user)
    rows = db.scalars(
        select(EvolutionCandidateRecord)
        .where(EvolutionCandidateRecord.run_id == run.id)
        .order_by(
            EvolutionCandidateRecord.score.desc(),
            EvolutionCandidateRecord.created_at.asc(),
        )
    ).all()
    return {
        **run_summary_payload(db, run),
        "candidates": [_candidate_record_payload(row) for row in rows],
    }


def create_artifact_review(
    db: Session,
    *,
    user: User,
    artifact_id: str,
    reviewed_through: date,
    limit: int,
    idempotent: bool = False,
) -> dict:
    artifact = _artifact_or_error(db, artifact_id=artifact_id, user=user)
    if reviewed_through <= artifact.cutoff_date:
        _fail(422, "复核截止日必须晚于当前资料截止日")
    if reviewed_through > _today():
        _fail(422, "复核截止日不能晚于今天")
    same_run = db.scalar(
        select(EvolutionReviewRun).where(
            EvolutionReviewRun.artifact_id == artifact.id,
            EvolutionReviewRun.reviewed_through == reviewed_through,
        )
    )
    if same_run is not None:
        if idempotent or _can_view(user, same_run.confidentiality):
            return get_review_run(db, run_id=same_run.id, user=user)
        _fail(409, "该复核截止日已经存在批次")
    active_run = db.scalar(
        select(EvolutionReviewRun).where(
            EvolutionReviewRun.artifact_id == artifact.id,
            EvolutionReviewRun.status.in_(ACTIVE_RUN_STATUSES),
        )
    )
    if active_run is not None:
        _fail(409, "该维护资料已有未完成复核批次")

    digest = create_evolution_digest(
        db,
        user=user,
        artifact=artifact.artifact_type,
        cutoff_date=artifact.cutoff_date,
        reviewed_through=reviewed_through,
        audience=artifact.audience,
        limit=limit,
    )
    candidate_levels = [
        item.get("primary_source", {}).get("confidentiality", "L1")
        for item in digest["candidates"]
    ]
    confidentiality = _highest_confidentiality(
        artifact.confidentiality,
        *candidate_levels,
    )
    summary = {
        key: value
        for key, value in digest.items()
        if key not in {"candidates", "missing_evidence"}
    }
    summary["missing_evidence_count"] = len(digest["missing_evidence"])
    summary["persisted_candidate_count"] = len(digest["candidates"])
    run = EvolutionReviewRun(
        artifact_id=artifact.id,
        cutoff_date=artifact.cutoff_date,
        reviewed_through=reviewed_through,
        confidentiality=confidentiality,
        generation_mode=digest["generation_mode"],
        summary_json=json.dumps(
            summary,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ),
        created_by_user_id=user.id,
    )
    db.add(run)
    db.flush()
    document_ids: list[str] = []
    for item in digest["candidates"]:
        source = item["primary_source"]
        document = db.get(Document, source["document_id"])
        if document is None:
            continue
        document_ids.append(document.id)
        review_status = (
            "deferred" if item["score_band"] == "defer" else "pending"
        )
        db.add(
            EvolutionCandidateRecord(
                run_id=run.id,
                artifact_id=artifact.id,
                candidate_key=item["candidate_id"],
                source_document_id=document.id,
                source_content_hash=document.content_hash,
                target_section=item["target_section"],
                suggested_action=item["suggested_action"],
                classification=item["classification"],
                score_band=item["score_band"],
                score=item["score"],
                disclosure_status=item["disclosure_status"],
                review_status=review_status,
                payload_json=json.dumps(
                    item,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ),
            )
        )
    _audit(
        db,
        user_id=user.id,
        action="evolution_review_started",
        document_ids=document_ids,
        details={
            "artifact_id": artifact.id,
            "run_id": run.id,
            "cutoff_date": artifact.cutoff_date.isoformat(),
            "reviewed_through": reviewed_through.isoformat(),
            "candidate_count": len(document_ids),
            "confidentiality": confidentiality,
        },
    )
    db.commit()
    return get_review_run(db, run_id=run.id, user=user)


def _candidate_source_reason(
    db: Session,
    candidate: EvolutionCandidateRecord,
) -> str | None:
    document = db.get(Document, candidate.source_document_id)
    if document is None:
        return "候选来源文档不存在"
    if document.content_hash != candidate.source_content_hash:
        return "候选来源身份已变化，请重新生成复核批次"
    if document.knowledge_status != "current" or document.valid_to is not None:
        return "候选来源已不再是当前资料，请重新生成复核批次"
    if (
        document.project.knowledge_status != "current"
        or not document.project.confirmed
    ):
        return "候选来源所属项目已不再是已确认当前项目"
    if document.role in FINAL_REQUIRED_ROLES and not document.is_final:
        return "候选来源不再是已确认定稿"
    if not any(chunk.text.strip() for chunk in document.chunks):
        return "候选来源缺少可引用正文"
    health = db.get(SourceHealth, document.content_hash)
    if not source_is_available(document.file_blob, health):
        return "候选来源原件不可用或完整性校验失败"
    return None


def decide_candidate(
    db: Session,
    *,
    user: User,
    candidate_id: str,
    decision: str,
    confirmation: str,
    note: str | None,
) -> dict:
    _require_founder(user)
    candidate = db.get(EvolutionCandidateRecord, candidate_id)
    if candidate is None:
        _fail(404, "知识进化候选不存在")
    run = _run_or_error(db, run_id=candidate.run_id, user=user)
    artifact = db.get(MaintainedArtifact, candidate.artifact_id)
    assert artifact is not None
    if run.status != "open":
        _fail(409, "该复核批次已冻结，不能修改候选决定")
    if candidate.review_status not in {"pending", "deferred"}:
        _fail(409, "该候选已经完成决策")
    if candidate.classification == "conflict":
        _fail(409, "冲突候选必须先治理来源，不能通过单项审批绕过")
    if decision == "reject":
        if confirmation != "确认不纳入":
            _fail(422, "退回候选需要输入：确认不纳入")
        candidate.review_status = "rejected"
    elif decision == "approve":
        expected = (
            "确认纳入并允许对外披露"
            if artifact.audience == "external"
            else "确认纳入变更计划"
        )
        if confirmation != expected:
            _fail(422, f"纳入候选需要输入：{expected}")
        reason = _candidate_source_reason(db, candidate)
        if reason:
            _fail(409, reason)
        candidate.review_status = "accepted"
        candidate.disclosure_status = (
            "approved_external"
            if artifact.audience == "external"
            else "not_required_internal"
        )
    else:
        _fail(422, "不支持的候选决定")
    candidate.decided_by_user_id = user.id
    candidate.decision_note = note.strip() if note else None
    candidate.decided_at = datetime.now(timezone.utc)
    _audit(
        db,
        user_id=user.id,
        action="evolution_candidate_decided",
        document_ids=[candidate.source_document_id],
        details={
            "artifact_id": artifact.id,
            "run_id": run.id,
            "candidate_id": candidate.id,
            "decision": candidate.review_status,
            "disclosure_status": candidate.disclosure_status,
        },
    )
    db.commit()
    db.refresh(candidate)
    return _candidate_record_payload(candidate)


def _accepted_candidates(
    db: Session,
    run_id: str,
) -> list[EvolutionCandidateRecord]:
    return list(
        db.scalars(
            select(EvolutionCandidateRecord)
            .where(
                EvolutionCandidateRecord.run_id == run_id,
                EvolutionCandidateRecord.review_status == "accepted",
            )
            .order_by(
                EvolutionCandidateRecord.target_section.asc(),
                EvolutionCandidateRecord.score.desc(),
            )
        ).all()
    )


def create_change_plan(
    db: Session,
    *,
    user: User,
    run_id: str,
    confirmation: str,
) -> dict:
    _require_founder(user)
    if confirmation != "确认生成变更计划":
        _fail(422, "生成变更计划需要输入：确认生成变更计划")
    run = _run_or_error(db, run_id=run_id, user=user)
    existing = db.scalar(
        select(EvolutionChangePlan).where(EvolutionChangePlan.run_id == run.id)
    )
    if existing is not None:
        return _change_plan_payload(existing) or {}
    if run.status != "open":
        _fail(409, "该复核批次不能生成变更计划")
    candidates = db.scalars(
        select(EvolutionCandidateRecord).where(
            EvolutionCandidateRecord.run_id == run.id
        )
    ).all()
    if any(row.classification == "conflict" for row in candidates):
        _fail(409, "存在来源冲突，解决冲突并重新复核后才能生成变更计划")
    unresolved = [
        row
        for row in candidates
        if row.score_band in REVIEWABLE_SCORE_BANDS
        and row.review_status == "pending"
    ]
    if unresolved:
        _fail(409, "仍有高价值候选未完成审批")
    artifact = db.get(MaintainedArtifact, run.artifact_id)
    assert artifact is not None
    baseline = db.get(Document, artifact.current_document_id)
    if baseline is None:
        _fail(409, "维护资料基线已不存在")
    accepted = _accepted_candidates(db, run.id)
    changes: list[dict] = []
    fingerprint_parts: list[dict] = []
    for candidate in accepted:
        reason = _candidate_source_reason(db, candidate)
        if reason:
            _fail(409, reason)
        if (
            artifact.audience == "external"
            and candidate.disclosure_status != "approved_external"
        ):
            _fail(409, "存在未获对外披露许可的已纳入候选")
        payload = _loads(candidate.payload_json, {})
        primary = payload.get("primary_source", {})
        changes.append(
            {
                "candidate_id": candidate.id,
                "target_section": candidate.target_section,
                "action": candidate.suggested_action,
                "current_content": {
                    "baseline_document_id": baseline.id,
                    "title": baseline.title,
                    "version": baseline.version,
                },
                "proposed_content": primary.get("excerpt"),
                "evidence": {
                    "primary_source": primary,
                    "corroborating_sources": payload.get(
                        "corroborating_sources",
                        [],
                    ),
                },
                "reason": payload.get("reason_new"),
                "confidence": payload.get("confidence"),
                "score": candidate.score,
            }
        )
        fingerprint_parts.append(
            {
                "candidate_id": candidate.id,
                "document_id": candidate.source_document_id,
                "content_hash": candidate.source_content_hash,
                "review_status": candidate.review_status,
                "disclosure_status": candidate.disclosure_status,
            }
        )
    source_fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_parts,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest().upper()
    plan_body = {
        "artifact": {
            "id": artifact.id,
            "name": artifact.name,
            "artifact_type": artifact.artifact_type,
            "audience": artifact.audience,
            "baseline_document_id": baseline.id,
        },
        "review_window": {
            "cutoff_date": run.cutoff_date.isoformat(),
            "reviewed_through": run.reviewed_through.isoformat(),
        },
        "changes": changes,
        "accepted_count": len(changes),
        "publication_status": "not_published",
        "automatic_publication": False,
        "next_action": (
            "按变更计划制作候选版，核对引用后另行发布新文档。"
            if changes
            else "本次无候选纳入，记录复核后保留当前版本。"
        ),
    }
    plan = EvolutionChangePlan(
        run_id=run.id,
        artifact_id=artifact.id,
        plan_json=json.dumps(
            plan_body,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        source_fingerprint=source_fingerprint,
        created_by_user_id=user.id,
    )
    db.add(plan)
    run.status = "plan_ready"
    db.flush()
    _audit(
        db,
        user_id=user.id,
        action="evolution_change_plan_created",
        document_ids=[row.source_document_id for row in accepted],
        details={
            "artifact_id": artifact.id,
            "run_id": run.id,
            "plan_id": plan.id,
            "accepted_count": len(changes),
            "source_fingerprint": source_fingerprint,
        },
    )
    db.commit()
    db.refresh(plan)
    return _change_plan_payload(plan) or {}


def close_review(
    db: Session,
    *,
    user: User,
    run_id: str,
    confirmation: str,
) -> dict:
    _require_founder(user)
    if confirmation != "确认完成本次复核":
        _fail(422, "完成复核需要输入：确认完成本次复核")
    run = _run_or_error(db, run_id=run_id, user=user)
    if run.status == "reviewed":
        return get_review_run(db, run_id=run.id, user=user)
    if run.status not in ACTIVE_RUN_STATUSES:
        _fail(409, "该复核批次不能完成")
    rows = db.scalars(
        select(EvolutionCandidateRecord).where(
            EvolutionCandidateRecord.run_id == run.id
        )
    ).all()
    if any(row.classification == "conflict" for row in rows):
        _fail(409, "存在来源冲突，不能完成本次复核")
    if any(
        row.score_band in REVIEWABLE_SCORE_BANDS
        and row.review_status == "pending"
        for row in rows
    ):
        _fail(409, "仍有高价值候选未完成审批")
    accepted_count = sum(row.review_status == "accepted" for row in rows)
    plan = db.scalar(
        select(EvolutionChangePlan).where(EvolutionChangePlan.run_id == run.id)
    )
    if accepted_count and plan is None:
        _fail(409, "已纳入候选必须先形成变更计划")
    artifact = db.get(MaintainedArtifact, run.artifact_id)
    assert artifact is not None
    old_cutoff = artifact.cutoff_date
    run.status = "reviewed"
    run.reviewed_by_user_id = user.id
    run.reviewed_at = datetime.now(timezone.utc)
    artifact.last_reviewed_at = run.reviewed_through
    artifact.next_review_at = run.reviewed_through + timedelta(
        days=artifact.review_cadence_days
    )
    if plan is not None:
        plan.status = "reviewed"
    _audit(
        db,
        user_id=user.id,
        action="evolution_review_completed",
        document_ids=[row.source_document_id for row in rows],
        details={
            "artifact_id": artifact.id,
            "run_id": run.id,
            "accepted_count": accepted_count,
            "cutoff_unchanged": artifact.cutoff_date == old_cutoff,
            "cutoff_date": artifact.cutoff_date.isoformat(),
            "next_review_at": artifact.next_review_at.isoformat(),
        },
    )
    db.commit()
    return get_review_run(db, run_id=run.id, user=user)


def update_artifact_baseline(
    db: Session,
    *,
    user: User,
    artifact_id: str,
    current_document_id: str,
    cutoff_date: date,
    confirmation: str,
) -> dict:
    _require_founder(user)
    if confirmation != "确认更新维护资料基线":
        _fail(422, "更新基线需要输入：确认更新维护资料基线")
    artifact = _artifact_or_error(db, artifact_id=artifact_id, user=user)
    if current_document_id == artifact.current_document_id:
        _fail(409, "新基线必须是另一个已经正式发布的文档版本")
    document = _validate_baseline(
        db,
        document_id=current_document_id,
        artifact_type=artifact.artifact_type,
        user=user,
    )
    if document.supersedes_document_id != artifact.current_document_id:
        _fail(409, "新基线必须沿正式发布链直接替代当前维护资料")
    effective_at = _effective_date(document)
    if cutoff_date < effective_at:
        _fail(422, "资料截止日不能早于新基线文档生效日")
    if cutoff_date > _today():
        _fail(422, "资料截止日不能晚于今天")
    old_document_id = artifact.current_document_id
    artifact.current_document_id = document.id
    artifact.cutoff_date = cutoff_date
    artifact.confidentiality = _highest_confidentiality(
        document.confidentiality,
        document.project.confidentiality,
    )
    artifact.last_reviewed_at = cutoff_date
    artifact.next_review_at = cutoff_date + timedelta(
        days=artifact.review_cadence_days
    )
    stale_runs = db.scalars(
        select(EvolutionReviewRun).where(
            EvolutionReviewRun.artifact_id == artifact.id,
            EvolutionReviewRun.status.in_(ACTIVE_RUN_STATUSES),
        )
    ).all()
    for run in stale_runs:
        run.status = "baseline_changed"
        plan = db.scalar(
            select(EvolutionChangePlan).where(
                EvolutionChangePlan.run_id == run.id
            )
        )
        if plan is not None:
            plan.status = "obsolete"
    _audit(
        db,
        user_id=user.id,
        action="maintained_artifact_baseline_updated",
        document_ids=[old_document_id, document.id],
        details={
            "artifact_id": artifact.id,
            "old_document_id": old_document_id,
            "new_document_id": document.id,
            "cutoff_date": cutoff_date.isoformat(),
            "invalidated_run_count": len(stale_runs),
        },
    )
    db.commit()
    db.refresh(artifact)
    return artifact_payload(db, artifact)


def run_due_artifact_reviews(
    db: Session,
    *,
    reviewed_through: date | None = None,
) -> dict:
    review_date = reviewed_through or _today()
    artifacts = db.scalars(
        select(MaintainedArtifact)
        .where(
            MaintainedArtifact.status == "active",
            MaintainedArtifact.next_review_at <= review_date,
        )
        .order_by(MaintainedArtifact.next_review_at.asc())
    ).all()
    generated: list[str] = []
    skipped: list[dict] = []
    for artifact in artifacts:
        owner = db.get(User, artifact.owner_user_id)
        if owner is None or not owner.active:
            skipped.append(
                {"artifact_id": artifact.id, "reason": "owner_unavailable"}
            )
            continue
        if review_date <= artifact.cutoff_date:
            skipped.append(
                {"artifact_id": artifact.id, "reason": "empty_review_window"}
            )
            continue
        active = db.scalar(
            select(EvolutionReviewRun.id).where(
                EvolutionReviewRun.artifact_id == artifact.id,
                EvolutionReviewRun.status.in_(ACTIVE_RUN_STATUSES),
            )
        )
        if active:
            skipped.append(
                {"artifact_id": artifact.id, "reason": "awaiting_review"}
            )
            continue
        try:
            result = create_artifact_review(
                db,
                user=owner,
                artifact_id=artifact.id,
                reviewed_through=review_date,
                limit=100,
                idempotent=True,
            )
        except EvolutionWorkflowError as exc:
            skipped.append(
                {"artifact_id": artifact.id, "reason": exc.detail}
            )
            continue
        generated.append(result["id"])
    return {
        "status": "ok",
        "reviewed_through": review_date,
        "due_count": len(artifacts),
        "generated_count": len(generated),
        "generated_run_ids": generated,
        "skipped": skipped,
        "automatic_publication": False,
        "generation_mode": "local_deterministic",
    }
