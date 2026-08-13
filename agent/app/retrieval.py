from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .embeddings import EmbeddingServiceError, request_embeddings
from .generation import (
    GenerationEvidence,
    GenerationServiceError,
    evidence_allowed,
    generate_grounded_answer,
)
from .models import (
    AuditLog,
    Chunk,
    ChunkEmbedding,
    Document,
    Project,
    SourceHealth,
    User,
)
from .source_integrity import source_is_available
from .contracts import CONTRACT_DOMAINS


CONFIDENTIALITY_RANK = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}
CURRENT_HINTS = ("当前", "最新", "现在", "现行", "公司介绍", "公司简介", "目前")
ASCII_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
CJK_RE = re.compile(r"[\u3400-\u9fff]+")


@dataclass
class SearchHit:
    chunk: Chunk
    document: Document
    project: Project
    score: float
    matched_terms: list[str]
    lexical_score: float = 0.0
    semantic_score: float | None = None


def query_terms(query: str) -> list[str]:
    normalized = query.strip().lower()
    terms: list[str] = [word.lower() for word in ASCII_WORD_RE.findall(normalized)]
    for sequence in CJK_RE.findall(normalized):
        if len(sequence) <= 2:
            terms.append(sequence)
        else:
            terms.append(sequence)
            terms.extend(sequence[index:index + 2] for index in range(len(sequence) - 1))
    return list(dict.fromkeys(term for term in terms if term.strip()))


def choose_scope(query: str, requested: str) -> tuple[str, str]:
    if requested != "auto":
        return requested, "request"
    if any(hint in query for hint in CURRENT_HINTS):
        return "current", "current-fact-hint"
    return "history", "historical-case-default"


def is_authorized(user: User, document: Document, project: Project) -> bool:
    ceiling = CONFIDENTIALITY_RANK.get(user.confidentiality_ceiling, 0)
    required = max(
        CONFIDENTIALITY_RANK.get(document.confidentiality, 99),
        CONFIDENTIALITY_RANK.get(project.confidentiality, 99),
    )
    if ceiling < required:
        return False
    # Project categories organize knowledge; they are not access-control
    # boundaries. Every active employee can work across categories, while the
    # confidentiality ceiling remains the mandatory authorization boundary.
    return True


def user_departments(user: User) -> set[str]:
    try:
        values = json.loads(user.departments_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return set()
    return {
        str(value)
        for value in values
        if isinstance(value, str) and value.strip()
    }


def _authorized_domains(user: User) -> tuple[str, ...]:
    # Company-wide material is visible to every employee subject to its
    # confidentiality level; business material stays within assigned lines.
    return tuple(sorted(user_departments(user) | {"company"}))


def _authorized_levels(
    user: User,
    *,
    include_contracts: bool = False,
) -> tuple[str, ...]:
    ceiling = CONFIDENTIALITY_RANK.get(user.confidentiality_ceiling, 0)
    # Administrative and HR accounts may hold L4/L5 clearance for the
    # dedicated local contract archive.  Their ordinary business-material
    # retrieval remains capped at L3.
    if (
        not include_contracts
        and user.organization_role in {"administrative", "personnel"}
    ):
        ceiling = min(ceiling, CONFIDENTIALITY_RANK["L3"])
    return tuple(
        level
        for level, rank in CONFIDENTIALITY_RANK.items()
        if rank <= ceiling
    )


def _allowed_statuses(scope: str) -> tuple[str, ...]:
    if scope == "current":
        return ("current",)
    if scope == "history":
        return ("current", "approved", "superseded", "archived")
    return ("current", "approved", "superseded", "archived")


def _status_allowed(document: Document, scope: str) -> bool:
    if scope == "current":
        return document.knowledge_status == "current" and document.valid_to is None
    if scope == "history":
        return document.knowledge_status in {"current", "approved", "superseded", "archived"}
    return document.knowledge_status in {"current", "approved", "superseded", "archived"}


def _score(query: str, terms: list[str], chunk: Chunk, document: Document, project: Project) -> tuple[float, list[str]]:
    text = chunk.text.lower()
    title = document.title.lower()
    project_name = project.name.lower()
    query_lower = query.lower().strip()
    score = 0.0
    matched: list[str] = []
    exact_query_match = False
    if query_lower and query_lower in text:
        score += 10.0
        exact_query_match = True
    if query_lower and query_lower in title:
        score += 14.0
        exact_query_match = True
    if query_lower and query_lower in project_name:
        score += 16.0
        exact_query_match = True
    for term in terms:
        count = min(text.count(term), 4)
        title_count = title.count(term)
        project_count = project_name.count(term)
        term_score = count * (2.0 if len(term) > 1 else 0.5)
        term_score += title_count * 4.0 + project_count * 5.0
        if term_score:
            matched.append(term)
            score += term_score

    # Freshness, final-state, and document-role bonuses may only rank an
    # already relevant hit. They must never turn an unrelated current/final
    # document into a result. For mixed natural-language and exact identifier
    # queries, require at least half of the high-signal ASCII anchors (years,
    # codes, IDs) to match so a generic word such as “电竞” cannot answer a
    # fabricated contract or event query.
    if not exact_query_match and not matched:
        return 0.0, []
    ascii_anchors = list(
        dict.fromkeys(
            term
            for term in ASCII_WORD_RE.findall(query_lower)
            if len(term) >= 3
        )
    )
    if ascii_anchors:
        matched_anchors = sum(
            1
            for anchor in ascii_anchors
            if anchor in text or anchor in title or anchor in project_name
        )
        required_anchors = max(1, math.ceil(len(ascii_anchors) / 2))
        if matched_anchors < required_anchors:
            return 0.0, []
    if document.is_final:
        score += 1.5
    if document.role == "closing_report":
        score += 1.0
    if document.knowledge_status == "current":
        score += 2.0
    return score, matched


def excerpt(text: str, terms: list[str], limit: int = 260) -> str:
    if len(text) <= limit:
        return text
    positions = [text.lower().find(term.lower()) for term in terms]
    positions = [position for position in positions if position >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - limit // 3)
    end = min(len(text), start + limit)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _semantic_requested(requested: str, scope: str) -> bool:
    if requested == "exact":
        return False
    if requested in {"semantic", "hybrid"}:
        return True
    return scope != "current"


def search(
    db: Session,
    *,
    user: User,
    query: str,
    requested_scope: str = "auto",
    requested_retrieval: str = "auto",
    limit: int = 8,
    audit: bool = True,
    category: str | None = None,
    generate: bool = True,
    include_contracts: bool = False,
    audit_action: str = "search",
) -> dict:
    scope, reason = choose_scope(query, requested_scope)
    terms = query_terms(query)
    if not terms:
        return {
            "query_id": None,
            "retrieval_mode": "exact",
            "retrieval_degraded": False,
            "scope": scope,
            "scope_reason": reason,
            "answer": "资料中未找到",
            "results": [],
            "citations": [],
            "generation_mode": "deterministic",
            "generation_model": None,
            "generation_fallback_used": False,
            "generation_degraded": False,
            "denied_count": 0,
            "unavailable_count": 0,
        }

    authorized_levels = _authorized_levels(
        user,
        include_contracts=include_contracts,
    )
    allowed_statuses = _allowed_statuses(scope)
    chunk_query = (
        select(Chunk)
        .join(Chunk.document)
        .join(Document.project)
        .options(
            joinedload(Chunk.document).joinedload(Document.project),
            joinedload(Chunk.document).joinedload(Document.file_blob),
        )
        .where(
            Document.confidentiality.in_(authorized_levels),
            Project.confidentiality.in_(authorized_levels),
            Document.knowledge_status.in_(allowed_statuses),
        )
    )
    if category:
        chunk_query = chunk_query.where(Project.domain == category)
    if not include_contracts:
        chunk_query = chunk_query.where(Project.domain.not_in(CONTRACT_DOMAINS))
    chunks = db.scalars(chunk_query).all()
    source_health = {
        row.content_hash: row
        for row in db.scalars(select(SourceHealth)).all()
    }
    lexical_hits: list[SearchHit] = []
    # Unauthorized rows never enter either candidate set. Keeping this at zero
    # also avoids turning administrative diagnostics into a document-count
    # side channel.
    denied = 0
    unavailable_document_ids: set[str] = set()
    for chunk in chunks:
        document = chunk.document
        project = document.project
        score, matched = _score(query, terms, chunk, document, project)
        if score <= 0:
            continue
        if (
            not source_is_available(
                document.file_blob,
                source_health.get(document.content_hash),
            )
        ):
            unavailable_document_ids.add(document.id)
            continue
        if not _status_allowed(document, scope):
            continue
        lexical_hits.append(
            SearchHit(
                chunk,
                document,
                project,
                score,
                matched,
                lexical_score=score,
            )
        )
    lexical_hits.sort(
        key=lambda item: (
            item.score,
            item.document.knowledge_status == "current",
            item.document.is_final,
            item.chunk.page,
        ),
        reverse=True,
    )

    retrieval_mode = "exact"
    retrieval_degraded = False
    semantic_hits: list[SearchHit] = []
    if (
        _semantic_requested(requested_retrieval, scope)
        and settings.embedding_enabled
        and settings.gateway_api_key
    ):
        embedding_count = db.scalar(
            select(ChunkEmbedding.id)
            .where(ChunkEmbedding.model_name == settings.embedding_model)
            .limit(1)
        )
        if embedding_count:
            try:
                query_vector = request_embeddings([query])[0]
                embedding_query = (
                    select(ChunkEmbedding)
                    .join(ChunkEmbedding.chunk)
                    .join(Chunk.document)
                    .join(Document.project)
                    .options(
                        joinedload(ChunkEmbedding.chunk)
                        .joinedload(Chunk.document)
                        .joinedload(Document.project),
                        joinedload(ChunkEmbedding.chunk)
                        .joinedload(Chunk.document)
                        .joinedload(Document.file_blob),
                    )
                    .where(
                        ChunkEmbedding.model_name == settings.embedding_model,
                        Document.confidentiality.in_(authorized_levels),
                        Project.confidentiality.in_(authorized_levels),
                        Document.knowledge_status.in_(allowed_statuses),
                        Document.confidentiality.not_in(("L4", "L5")),
                        Project.confidentiality.not_in(("L4", "L5")),
                    )
                )
                if category:
                    embedding_query = embedding_query.where(
                        Project.domain == category
                    )
                if not include_contracts:
                    embedding_query = embedding_query.where(
                        Project.domain.not_in(CONTRACT_DOMAINS)
                    )
                embedding_rows = db.scalars(embedding_query).all()
                for row in embedding_rows:
                    chunk = row.chunk
                    document = chunk.document
                    project = document.project
                    # SQL has already applied authorization, knowledge status
                    # and L4/L5 exclusion before rows reach similarity scoring.
                    if (
                        not source_is_available(
                            document.file_blob,
                            source_health.get(document.content_hash),
                        )
                        or not _status_allowed(document, scope)
                    ):
                        continue
                    similarity = cosine_similarity(query_vector, row.embedding)
                    if similarity <= 0:
                        continue
                    semantic_hits.append(
                        SearchHit(
                            chunk,
                            document,
                            project,
                            similarity,
                            [],
                            lexical_score=0.0,
                            semantic_score=similarity,
                        )
                    )
                semantic_hits.sort(
                    key=lambda item: item.semantic_score or 0.0,
                    reverse=True,
                )
                retrieval_mode = (
                    "semantic"
                    if requested_retrieval == "semantic"
                    else "hybrid"
                )
            except (EmbeddingServiceError, IndexError):
                retrieval_degraded = True

    if retrieval_mode == "exact":
        hits = lexical_hits
    else:
        by_chunk: dict[str, SearchHit] = {}
        rrf_scores: dict[str, float] = {}
        if retrieval_mode != "semantic":
            for rank, hit in enumerate(lexical_hits[:100], start=1):
                by_chunk[hit.chunk.id] = hit
                rrf_scores[hit.chunk.id] = rrf_scores.get(hit.chunk.id, 0.0) + (
                    1.0 / (60 + rank)
                )
        for rank, hit in enumerate(semantic_hits[:100], start=1):
            current = by_chunk.get(hit.chunk.id)
            if current:
                current.semantic_score = hit.semantic_score
            else:
                by_chunk[hit.chunk.id] = hit
            rrf_scores[hit.chunk.id] = rrf_scores.get(hit.chunk.id, 0.0) + (
                1.0 / (60 + rank)
            )
        hits = []
        for chunk_id, hit in by_chunk.items():
            hit.score = rrf_scores[chunk_id] * 1000
            hits.append(hit)
        hits.sort(key=lambda item: item.score, reverse=True)

    selected: list[SearchHit] = []
    seen_pages: set[tuple[str, int]] = set()
    for hit in hits:
        key = (hit.document.id, hit.chunk.page)
        if key in seen_pages:
            continue
        seen_pages.add(key)
        selected.append(hit)
        if len(selected) >= max(1, min(limit, 20)):
            break

    selected_documents: list[SearchHit] = []
    seen_documents: set[str] = set()
    result_limit = max(1, min(limit, 20))
    for hit in hits:
        if hit.document.id in seen_documents:
            continue
        seen_documents.add(hit.document.id)
        selected_documents.append(hit)
        if len(selected_documents) >= result_limit:
            break

    matched_pages_by_document: dict[str, list[int]] = {}
    for hit in hits:
        document_pages = matched_pages_by_document.setdefault(
            hit.document.id,
            [],
        )
        if hit.chunk.page not in document_pages:
            document_pages.append(hit.chunk.page)

    results = [
        {
            "document_id": hit.document.id,
            "title": hit.document.title,
            "version": hit.document.version,
            "page": hit.chunk.page,
            "citation_basis": hit.document.citation_basis,
            "project_id": hit.project.id,
            "project": hit.project.name,
            "domain": hit.project.domain,
            "knowledge_status": hit.document.knowledge_status,
            "confidentiality": hit.document.confidentiality,
            "effective_confidentiality": max(
                [hit.document.confidentiality, hit.project.confidentiality],
                key=lambda level: CONFIDENTIALITY_RANK.get(level, 99),
            ),
            "matched_pages": matched_pages_by_document.get(
                hit.document.id,
                [hit.chunk.page],
            )[:12],
            "excerpt": excerpt(hit.chunk.text, hit.matched_terms),
            "score": round(hit.score, 3),
            "score_breakdown": {
                "lexical": round(hit.lexical_score, 3),
                "semantic": (
                    round(hit.semantic_score, 6)
                    if hit.semantic_score is not None
                    else None
                ),
                "freshness": 2.0 if hit.document.knowledge_status == "current" else 0.0,
                "fusion": (
                    round(hit.score, 6)
                    if retrieval_mode in {"hybrid", "semantic"}
                    else None
                ),
            },
        }
        for hit in selected_documents
    ]
    citations = [
        {
            "document_id": item["document_id"],
            "title": item["title"],
            "version": item["version"],
            "page": item["page"],
            "citation_basis": item["citation_basis"],
        }
        for item in results
    ]
    if not results:
        answer = "资料中未找到"
    elif all(item["knowledge_status"] != "current" for item in results):
        answer = (
            f"找到 {len(results)} 条已确认的历史资料。"
            "这些资料可用于案例学习，但不代表公司当前口径。"
        )
    else:
        answer = f"找到 {len(results)} 条有来源的相关资料，请结合下方引用核验。"

    generation_mode = "deterministic"
    generation_model = None
    generation_fallback_used = False
    generation_degraded = False
    generation_error = None
    generation_outbound_characters = 0
    generation_outbound_document_ids: list[str] = []
    generation_evidence = [
        GenerationEvidence(
            document_id=hit.document.id,
            title=hit.document.title,
            version=hit.document.version,
            page=hit.chunk.page,
            status=hit.document.knowledge_status,
            confidentiality=max(
                [
                    hit.document.confidentiality,
                    hit.project.confidentiality,
                ],
                key=lambda level: CONFIDENTIALITY_RANK.get(level, 99),
            ),
            excerpt=excerpt(hit.chunk.text, hit.matched_terms),
        )
        for hit in selected
    ]
    if (
        generate
        and results
        and getattr(settings, "llm_enabled", False)
        and settings.gateway_api_key
    ):
        evidence_ranks = [
            CONFIDENTIALITY_RANK.get(item.confidentiality, 99)
            for item in generation_evidence
        ]
        mixed_scope_blocked = any(
            rank >= CONFIDENTIALITY_RANK["L4"]
            or (
                rank == CONFIDENTIALITY_RANK["L3"]
                and not (
                    user.role == "founder"
                    and getattr(settings, "llm_l3_enabled", False)
                )
            )
            for rank in evidence_ranks
        )
        eligible_evidence = [
            item
            for item in generation_evidence
            if evidence_allowed(item.confidentiality, founder=user.role == "founder")
        ]
        generation_outbound_document_ids = list(
            dict.fromkeys(item.document_id for item in eligible_evidence[:8])
        )
        if mixed_scope_blocked:
            generation_mode = "local_only"
            generation_error = "mixed_confidentiality_local_only"
            generation_outbound_document_ids = []
        else:
            try:
                generated = generate_grounded_answer(
                    query,
                    generation_evidence,
                    founder=user.role == "founder",
                )
                answer = generated.answer
                generation_mode = "llm"
                generation_model = generated.model
                generation_fallback_used = generated.fallback_used
                generation_outbound_characters = generated.outbound_characters
                generation_outbound_document_ids = (
                    generated.evidence_document_ids
                )
            except GenerationServiceError as exc:
                generation_error = str(exc)
                if generation_error == "no_outbound_evidence":
                    generation_mode = "local_only"
                else:
                    generation_degraded = True

    query_id = None
    if audit:
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        audit_log = AuditLog(
            user_id=user.id,
            action=audit_action,
            query_hash=query_hash,
            document_ids_json=json.dumps(
                list(dict.fromkeys(item["document_id"] for item in results))
            ),
            denied_count=denied,
            details_json=json.dumps(
                {
                    "scope": scope,
                    "scope_reason": reason,
                    "retrieval_mode": retrieval_mode,
                    "retrieval_degraded": retrieval_degraded,
                    "result_count": len(results),
                    "unavailable_count": len(unavailable_document_ids),
                    "generation_mode": generation_mode,
                    "generation_degraded": generation_degraded,
                    "organization_role": user.organization_role,
                    "ordinary_business_retrieval_ceiling": (
                        "L3"
                        if not include_contracts
                        and user.organization_role
                        in {"administrative", "personnel"}
                        else user.confidentiality_ceiling
                    ),
                },
                ensure_ascii=False,
            ),
        )
        db.add(audit_log)
        if (
            generate
            and
            getattr(settings, "llm_enabled", False)
            and settings.gateway_api_key
            and results
        ):
            db.add(
                AuditLog(
                    user_id=user.id,
                    action=(
                        "llm_generation"
                        if generation_mode == "llm"
                        else "llm_generation_skipped"
                        if generation_mode == "local_only"
                        else "llm_generation_failed"
                    ),
                    query_hash=query_hash,
                    document_ids_json=json.dumps(
                        generation_outbound_document_ids
                    ),
                    details_json=json.dumps(
                        {
                            "scope": scope,
                            "model": generation_model,
                            "fallback_used": generation_fallback_used,
                            "outbound_characters": (
                                generation_outbound_characters
                            ),
                            "error_code": generation_error,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
        db.commit()
        query_id = audit_log.id
    return {
        "query_id": query_id,
        "retrieval_mode": retrieval_mode,
        "retrieval_degraded": retrieval_degraded,
        "scope": scope,
        "scope_reason": reason,
        "answer": answer,
        "results": results,
        "citations": citations,
        "generation_mode": generation_mode,
        "generation_model": generation_model,
        "generation_fallback_used": generation_fallback_used,
        "generation_degraded": generation_degraded,
        "denied_count": denied if user.role in {"founder", "knowledge_admin"} else 0,
        "unavailable_count": (
            len(unavailable_document_ids)
            if user.role in {"founder", "knowledge_admin"}
            else 0
        ),
    }
