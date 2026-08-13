from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import User, WritingDraft


MAX_SAVED_WRITING_DRAFTS = 5
_SOURCE_TEXT_FIELDS = (
    "document_id",
    "title",
    "version",
    "citation_basis",
    "project_id",
    "project",
    "domain",
    "knowledge_status",
    "confidentiality",
    "effective_confidentiality",
    "role",
)
_RESPONSE_FIELDS = (
    "generation_mode",
    "generation_model",
    "generation_degraded",
    "retrieval_mode",
    "retrieval_degraded",
    "effective_category",
    "effective_category_name",
    "category_auto_inferred",
    "restricted_source_count",
    "l3_authorized_for_request",
    "notice",
)


def _json_load(value: str, fallback):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _title(value: str | None, instruction: str) -> str:
    if value and value.strip():
        return value.strip()[:200]
    first_line = next(
        (line.strip() for line in instruction.splitlines() if line.strip()),
        "未命名创作",
    )
    return first_line[:60]


def _content_hash(instruction: str, content: str) -> str:
    return hashlib.sha256(
        f"{instruction.strip()}\n\0{content}".encode("utf-8")
    ).hexdigest()


def _sanitize_sources(sources: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for item in sources[:100]:
        if not isinstance(item, dict) or not item.get("document_id"):
            continue
        source = {
            key: str(item[key])[:500]
            for key in _SOURCE_TEXT_FIELDS
            if item.get(key) is not None
        }
        try:
            source["page"] = max(1, int(item.get("page") or 1))
        except (TypeError, ValueError):
            source["page"] = 1
        pages = item.get("matched_pages")
        if isinstance(pages, list):
            source["matched_pages"] = [
                int(page) for page in pages[:50] if isinstance(page, int) and page > 0
            ]
        cleaned.append(source)
    return cleaned


def _restore_sources(sources: list[dict]) -> list[dict]:
    return [
        {
            **item,
            "excerpt": "",
            "score": 0,
            "citation_basis": item.get("citation_basis", "source-page"),
            "project_id": item.get("project_id", ""),
            "project": item.get("project", ""),
            "domain": item.get("domain", ""),
            "knowledge_status": item.get("knowledge_status", "approved"),
            "confidentiality": item.get(
                "confidentiality",
                item.get("effective_confidentiality", "L1"),
            ),
        }
        for item in sources
    ]


def _sanitize_response(response: dict, *, content: str, sources: list[dict]) -> dict:
    cleaned = {
        key: response[key]
        for key in _RESPONSE_FIELDS
        if key in response
        and isinstance(response[key], (str, int, float, bool, type(None)))
    }
    if isinstance(cleaned.get("notice"), str):
        cleaned["notice"] = cleaned["notice"][:2000]
    cleaned["draft"] = content
    cleaned["sources"] = sources
    return cleaned


def _lock_owner(db: Session, user_id: str) -> None:
    # PostgreSQL serializes saves for one user so concurrent requests cannot
    # both observe four saved drafts and create a sixth item.
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())


def serialize_writing_draft(record: WritingDraft) -> dict:
    sources = _restore_sources(_json_load(record.sources_json, []))
    response = _json_load(record.response_json, {})
    response["sources"] = sources
    response["draft"] = record.content
    return {
        "id": record.id,
        "title": record.title,
        "instruction": record.instruction,
        "draft": record.content,
        "content": record.content,
        "category": record.category,
        "scope": record.scope,
        "time_scope": record.time_scope,
        "generation_mode": record.generation_mode,
        "generation_model": record.generation_model,
        "sources": sources,
        "response": response,
        "auto_saved": record.kind == "latest",
        "kind": record.kind,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def list_writing_drafts(db: Session, *, user_id: str) -> dict:
    latest = db.scalar(
        select(WritingDraft)
        .where(
            WritingDraft.user_id == user_id,
            WritingDraft.kind == "latest",
        )
        .order_by(WritingDraft.updated_at.desc())
    )
    saved = db.scalars(
        select(WritingDraft)
        .where(
            WritingDraft.user_id == user_id,
            WritingDraft.kind == "saved",
        )
        .order_by(WritingDraft.updated_at.desc(), WritingDraft.created_at.desc())
    ).all()
    return {
        "latest": serialize_writing_draft(latest) if latest else None,
        "saved": [serialize_writing_draft(item) for item in saved],
        "saved_count": len(saved),
        "max_saved": MAX_SAVED_WRITING_DRAFTS,
    }


def upsert_latest_writing_draft(
    db: Session,
    *,
    user_id: str,
    instruction: str,
    content: str,
    category: str | None,
    scope: str,
    generation_mode: str | None,
    generation_model: str | None,
    sources: list[dict],
    response: dict,
    title: str | None = None,
) -> WritingDraft:
    _lock_owner(db, user_id)
    latest_rows = db.scalars(
        select(WritingDraft)
        .where(
            WritingDraft.user_id == user_id,
            WritingDraft.kind == "latest",
        )
        .order_by(WritingDraft.updated_at.desc())
        .with_for_update()
    ).all()
    record = latest_rows[0] if latest_rows else WritingDraft(user_id=user_id, kind="latest")
    for duplicate in latest_rows[1:]:
        db.delete(duplicate)
    now = datetime.now(timezone.utc)
    record.title = _title(title, instruction)
    record.instruction = instruction
    record.content = content
    record.category = category
    record.scope = scope
    record.time_scope = scope
    record.generation_mode = generation_mode
    record.generation_model = generation_model
    safe_sources = _sanitize_sources(sources)
    safe_response = _sanitize_response(response, content=content, sources=safe_sources)
    record.sources_json = json.dumps(safe_sources, ensure_ascii=False)
    record.response_json = json.dumps(safe_response, ensure_ascii=False, default=str)
    record.content_hash = _content_hash(instruction, content)
    record.updated_at = now
    if not latest_rows:
        record.created_at = now
        db.add(record)
    db.flush()
    return record


def save_writing_snapshot(
    db: Session,
    *,
    user_id: str,
    title: str | None,
    instruction: str,
    content: str,
    category: str | None,
    scope: str,
    time_scope: str | None,
    generation_mode: str | None,
    generation_model: str | None,
    sources: list[dict],
    response: dict,
) -> tuple[WritingDraft, int, bool]:
    _lock_owner(db, user_id)
    fingerprint = _content_hash(instruction, content)
    duplicate = db.scalar(
        select(WritingDraft)
        .where(
            WritingDraft.user_id == user_id,
            WritingDraft.kind == "saved",
            WritingDraft.content_hash == fingerprint,
        )
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if duplicate is not None:
        duplicate.title = _title(title, instruction)
        duplicate.category = category
        duplicate.scope = scope
        duplicate.time_scope = time_scope or scope
        duplicate.generation_mode = generation_mode
        duplicate.generation_model = generation_model
        safe_sources = _sanitize_sources(sources)
        safe_response = _sanitize_response(response, content=content, sources=safe_sources)
        duplicate.sources_json = json.dumps(safe_sources, ensure_ascii=False)
        duplicate.response_json = json.dumps(safe_response, ensure_ascii=False, default=str)
        duplicate.updated_at = now
        db.flush()
        count = db.scalar(
            select(func.count(WritingDraft.id)).where(
                WritingDraft.user_id == user_id,
                WritingDraft.kind == "saved",
            )
        ) or 0
        return duplicate, int(count), True

    count = db.scalar(
        select(func.count(WritingDraft.id)).where(
            WritingDraft.user_id == user_id,
            WritingDraft.kind == "saved",
        )
    ) or 0
    if count >= MAX_SAVED_WRITING_DRAFTS:
        raise OverflowError("每个用户最多保存5条创作，请先删除一条已保存创作后再试。")
    safe_sources = _sanitize_sources(sources)
    safe_response = _sanitize_response(response, content=content, sources=safe_sources)
    record = WritingDraft(
        user_id=user_id,
        kind="saved",
        title=_title(title, instruction),
        instruction=instruction,
        content=content,
        category=category,
        scope=scope,
        time_scope=time_scope or scope,
        generation_mode=generation_mode,
        generation_model=generation_model,
        sources_json=json.dumps(safe_sources, ensure_ascii=False),
        response_json=json.dumps(safe_response, ensure_ascii=False, default=str),
        content_hash=fingerprint,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    return record, int(count) + 1, False
