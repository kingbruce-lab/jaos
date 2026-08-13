from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import AuditLog, Document, Project, SourceHealth, User
from .retrieval import CONFIDENTIALITY_RANK
from .source_integrity import source_is_available


SUPPORTED_ROLES = {
    "company_profile",
    "execution",
    "closing_report",
    "asset",
}
FINAL_REQUIRED_ROLES = {
    "company_profile",
    "execution",
    "closing_report",
}
TARGET_SECTIONS = {
    "company_profile": "company_overview",
    "execution": "milestones",
    "closing_report": "representative_cases",
    "asset": "visual_assets",
}
SUGGESTED_ACTIONS = {
    "company_profile": "update",
    "execution": "update",
    "closing_report": "add",
    "asset": "add",
}
ROLE_SIGNIFICANCE = {
    "company_profile": 5,
    "closing_report": 5,
    "execution": 4,
    "asset": 3,
}
ROLE_EVIDENCE = {
    "company_profile": 5,
    "closing_report": 5,
    "execution": 4,
    "asset": 3,
}
ARTIFACT_LABELS = {
    "company_profile": "公司介绍",
    "capability_deck": "公司能力介绍",
    "case_library": "案例库",
    "team_profile": "战队与专家介绍",
}
WHITESPACE_RE = re.compile(r"\s+")


def _effective_date(document: Document) -> date:
    value = document.valid_from or document.ingested_at
    return value.date()


def _best_chunk(document: Document):
    chunks = sorted(
        (chunk for chunk in document.chunks if chunk.text.strip()),
        key=lambda chunk: (
            0 if chunk.page > 0 else 1,
            chunk.chunk_index,
        ),
    )
    if not chunks:
        return None
    if document.role in {"closing_report", "execution"}:
        result_hints = (
            "结果",
            "成果",
            "完成",
            "验收",
            "成绩",
            "数据",
            "活动",
        )
        for chunk in chunks:
            if any(hint in chunk.text for hint in result_hints):
                return chunk
    return chunks[0]


def _excerpt(text: str, limit: int = 360) -> str:
    normalized = WHITESPACE_RE.sub(" ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}…"


def _freshness_score(effective_at: date, reviewed_through: date) -> int:
    age = max((reviewed_through - effective_at).days, 0)
    if age <= 30:
        return 5
    if age <= 90:
        return 4
    if age <= 180:
        return 3
    if age <= 365:
        return 2
    return 1


def _audience_score(artifact: str, role: str) -> int:
    if artifact == "company_profile":
        return {
            "company_profile": 5,
            "closing_report": 4,
            "execution": 4,
            "asset": 4,
        }.get(role, 2)
    if artifact == "capability_deck":
        return {
            "company_profile": 4,
            "closing_report": 4,
            "execution": 5,
            "asset": 4,
        }.get(role, 2)
    if artifact == "case_library":
        return {
            "company_profile": 2,
            "closing_report": 5,
            "execution": 5,
            "asset": 4,
        }.get(role, 2)
    return {
        "company_profile": 3,
        "closing_report": 3,
        "execution": 3,
        "asset": 4,
    }.get(role, 2)


def _visual_score(document: Document) -> int:
    if document.role == "asset":
        return 5
    ready_visual = any(
        artifact.status == "ready"
        and artifact.kind in {"page_png", "preview", "rendered_pages"}
        for artifact in document.artifacts
    )
    return 3 if ready_visual else 2


def _score_candidate(
    document: Document,
    *,
    artifact: str,
    reviewed_through: date,
) -> tuple[dict[str, int], int, str]:
    breakdown = {
        "significance": ROLE_SIGNIFICANCE[document.role],
        "evidence": ROLE_EVIDENCE[document.role],
        "freshness": _freshness_score(
            _effective_date(document),
            reviewed_through,
        ),
        "audience_relevance": _audience_score(artifact, document.role),
        "visual_quality": _visual_score(document),
        # First release proves novelty by approved effective date only. A
        # content-level comparison starts after maintained artifacts exist.
        "novelty": 3,
    }
    score = round(sum(breakdown.values()) / 30 * 100)
    if score >= 80:
        band = "material"
    elif score >= 60:
        band = "review"
    else:
        band = "defer"
    return breakdown, score, band


def _source_payload(document: Document) -> dict:
    chunk = _best_chunk(document)
    return {
        "document_id": document.id,
        "title": document.title,
        "version": document.version,
        "role": document.role,
        "page": chunk.page if chunk else None,
        "excerpt": _excerpt(chunk.text) if chunk else None,
        "effective_at": _effective_date(document).isoformat(),
        "project": {
            "id": document.project.id,
            "name": document.project.name,
            "client": document.project.client,
            "year": document.project.year,
            "domain": document.project.domain,
        },
        "confidentiality": document.confidentiality,
        "source_available": True,
    }


def _candidate_payload(
    document: Document,
    *,
    artifact: str,
    audience: str,
    reviewed_through: date,
    corroborating: list[Document] | None = None,
    conflict: bool = False,
) -> dict:
    breakdown, score, score_band = _score_candidate(
        document,
        artifact=artifact,
        reviewed_through=reviewed_through,
    )
    disclosure_status = (
        "not_required_internal"
        if audience == "internal"
        else "needs_founder_approval"
    )
    hard_gate_failures: list[str] = []
    if conflict:
        hard_gate_failures.append("conflicting_current_sources")
    if audience == "external":
        hard_gate_failures.append("external_disclosure_unapproved")
    classification = (
        "conflict"
        if conflict
        else "blocked"
        if hard_gate_failures
        else score_band
    )
    return {
        "candidate_id": (
            f"conflict:{document.project_id}:{document.role}"
            if conflict
            else f"document:{document.id}"
        ),
        "target_section": TARGET_SECTIONS[document.role],
        "suggested_action": (
            "conflict" if conflict else SUGGESTED_ACTIONS[document.role]
        ),
        "classification": classification,
        "score_band": score_band,
        "score": score,
        "score_breakdown": breakdown,
        "primary_source": _source_payload(document),
        "corroborating_sources": [
            _source_payload(item) for item in (corroborating or [])
        ],
        "disclosure_status": disclosure_status,
        "hard_gate_failures": hard_gate_failures,
        "confidence": (
            "high" if breakdown["evidence"] >= 5 else "medium"
        ),
        "reason_new": (
            "该资料的已确认生效日期晚于当前资料截止日；"
            "首期尚未登记当前成品的逐页内容映射，仍需人工核对是否重复。"
        ),
    }


def _allowed_levels(user: User) -> tuple[str, ...]:
    ceiling = CONFIDENTIALITY_RANK.get(user.confidentiality_ceiling, 0)
    return tuple(
        level
        for level, rank in CONFIDENTIALITY_RANK.items()
        if rank <= ceiling
    )


def create_evolution_digest(
    db: Session,
    *,
    user: User,
    artifact: str,
    cutoff_date: date,
    reviewed_through: date,
    audience: str,
    limit: int,
) -> dict:
    allowed_levels = _allowed_levels(user)
    documents = db.scalars(
        select(Document)
        .join(Document.project)
        .options(
            joinedload(Document.project),
            joinedload(Document.file_blob),
            joinedload(Document.chunks),
            joinedload(Document.artifacts),
        )
        .where(
            Document.confidentiality.in_(allowed_levels),
            Project.confidentiality.in_(allowed_levels),
            Document.knowledge_status == "current",
            Document.valid_to.is_(None),
            Project.knowledge_status == "current",
            Project.confirmed.is_(True),
            Document.role.in_(SUPPORTED_ROLES),
        )
        .order_by(Document.valid_from.desc(), Document.ingested_at.desc())
    ).unique().all()
    source_health = {
        row.content_hash: row
        for row in db.scalars(select(SourceHealth)).all()
    }
    missing_evidence: list[dict] = []
    eligible_documents: list[Document] = []
    excluded_counts: dict[str, int] = defaultdict(int)
    for document in documents:
        effective_at = _effective_date(document)
        if not cutoff_date < effective_at <= reviewed_through:
            excluded_counts["outside_review_window"] += 1
            continue
        if (
            document.role in FINAL_REQUIRED_ROLES
            and not document.is_final
        ):
            excluded_counts["not_final"] += 1
            missing_evidence.append(
                {
                    "document_id": document.id,
                    "title": document.title,
                    "reason": "not_final",
                }
            )
            continue
        health = source_health.get(document.content_hash)
        if health is None or not source_is_available(document.file_blob, health):
            excluded_counts["source_unavailable"] += 1
            missing_evidence.append(
                {
                    "document_id": document.id,
                    "title": document.title,
                    "reason": "source_unavailable",
                }
            )
            continue
        if _best_chunk(document) is None:
            excluded_counts["no_citable_content"] += 1
            missing_evidence.append(
                {
                    "document_id": document.id,
                    "title": document.title,
                    "reason": "no_citable_content",
                }
            )
            continue
        eligible_documents.append(document)

    conflict_groups: dict[tuple[str, str], list[Document]] = defaultdict(list)
    for document in eligible_documents:
        conflict_groups[(document.project_id, document.role)].append(document)
    conflicts = {
        key: rows
        for key, rows in conflict_groups.items()
        if len({row.content_hash for row in rows}) > 1
    }
    conflict_ids = {
        document.id
        for rows in conflicts.values()
        for document in rows
    }

    candidates: list[dict] = []
    for rows in conflicts.values():
        primary, *others = sorted(
            rows,
            key=lambda item: (
                _effective_date(item),
                ROLE_EVIDENCE[item.role],
            ),
            reverse=True,
        )
        candidates.append(
            _candidate_payload(
                primary,
                artifact=artifact,
                audience=audience,
                reviewed_through=reviewed_through,
                corroborating=others,
                conflict=True,
            )
        )

    duplicate_count = 0
    deduplicated: dict[str, list[Document]] = defaultdict(list)
    for document in eligible_documents:
        if document.id in conflict_ids:
            continue
        deduplicated[document.content_hash].append(document)
    for rows in deduplicated.values():
        primary, *duplicates = sorted(
            rows,
            key=lambda item: (
                ROLE_EVIDENCE[item.role],
                _effective_date(item),
            ),
            reverse=True,
        )
        duplicate_count += len(duplicates)
        candidates.append(
            _candidate_payload(
                primary,
                artifact=artifact,
                audience=audience,
                reviewed_through=reviewed_through,
                corroborating=duplicates,
            )
        )

    candidates.sort(
        key=lambda item: (
            item["classification"] == "conflict",
            item["score"],
            item["primary_source"]["effective_at"],
        ),
        reverse=True,
    )
    candidates = candidates[:limit]
    counts = {
        name: sum(
            item["classification"] == name for item in candidates
        )
        for name in ("material", "review", "defer", "blocked", "conflict")
    }
    publishable_count = sum(
        item["classification"] in {"material", "review", "defer"}
        for item in candidates
    )
    if counts["conflict"]:
        next_action = "先解决当前资料冲突，再生成变更计划。"
    elif audience == "external" and candidates:
        next_action = (
            "由创始人逐项确认可对外披露范围；审批前不得写入公司介绍。"
        )
    elif counts["material"]:
        next_action = "由资料负责人审核高价值候选并形成逐页变更计划。"
    elif candidates:
        next_action = "人工复核候选；当前不触发成品资料更新。"
    else:
        next_action = "本周期没有合格候选，保留当前版本并记录复核。"

    generated_at = datetime.now(timezone.utc)
    result = {
        "artifact": {
            "type": artifact,
            "name": ARTIFACT_LABELS[artifact],
            "audience": audience,
        },
        "cutoff_date": cutoff_date.isoformat(),
        "reviewed_through": reviewed_through.isoformat(),
        "generated_at": generated_at,
        "eligible_count": len(eligible_documents),
        "publishable_count": publishable_count,
        "material_count": counts["material"],
        "review_count": counts["review"],
        "deferred_count": counts["defer"],
        "blocked_count": counts["blocked"],
        "conflict_count": counts["conflict"],
        "duplicate_count": duplicate_count,
        "excluded_counts": dict(sorted(excluded_counts.items())),
        "candidates": candidates,
        "missing_evidence": missing_evidence[:limit],
        "next_action": next_action,
        "automatic_publication": False,
        "generation_mode": "local_deterministic",
    }
    db.add(
        AuditLog(
            user_id=user.id,
            action="evolution_digest_generated",
            document_ids_json=json.dumps(
                sorted(
                    {
                        item["primary_source"]["document_id"]
                        for item in candidates
                    }
                )
            ),
            details_json=json.dumps(
                {
                    "artifact": artifact,
                    "audience": audience,
                    "cutoff_date": cutoff_date.isoformat(),
                    "reviewed_through": reviewed_through.isoformat(),
                    "eligible_count": len(eligible_documents),
                    "publishable_count": publishable_count,
                    "material_count": counts["material"],
                    "review_count": counts["review"],
                    "deferred_count": counts["defer"],
                    "blocked_count": counts["blocked"],
                    "conflict_count": counts["conflict"],
                    "duplicate_count": duplicate_count,
                    "excluded_counts": dict(excluded_counts),
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return result
