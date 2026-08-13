from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import (
    AuditLog,
    Chunk,
    Document,
    FileBlob,
    InboxIssue,
    KnowledgeCategory,
    Project,
)
from .parsers import chunk_text, parse_file
from .config import settings
from .contracts import contract_category_for_path, is_contract_archive_path
from .source_integrity import file_sha256, record_source_health


SUPPORTED_SUFFIXES = {
    ".pdf",
    ".pptx",
    ".doc",
    ".docm",
    ".docx",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".mp4",
    ".webm",
    ".mov",
    ".m4v",
    ".mp3",
    ".m4a",
    ".wav",
    ".flac",
    ".mm",
    ".ai",
    ".zip",
}
AUTO_APPROVED_ASSET_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".mp4",
    ".webm",
    ".mov",
    ".m4v",
    ".mp3",
    ".m4a",
    ".wav",
    ".flac",
    ".mm",
    ".ai",
    ".zip",
}
TEMPORARY_SUFFIXES = {".tmp", ".part", ".crdownload", ".download"}
TEMPORARY_NAME_RE = re.compile(r"\.~#\d+$", re.IGNORECASE)
# System-owned records are governed by their own workflow and permissions.  They
# must never be picked up by the knowledge-library scanner merely because the
# scanner is pointed at the shared NAS root.
SYSTEM_MANAGED_SCAN_EXCLUSIONS = {"财务系统"}
SYSTEM_MANAGED_SCAN_EXCLUSION_KEYS = frozenset(
    item.casefold() for item in SYSTEM_MANAGED_SCAN_EXCLUSIONS
)
GENERIC_FOLDERS = {
    "99_ai入库待审核",
    "ai入库待审核",
    "01_brief",
    "brief",
    "02_提案",
    "提案",
    "03_合同预算",
    "合同预算",
    "04_执行",
    "执行",
    "05_数据",
    "数据",
    "06_结案",
    "结案",
    "07_复盘素材",
    "复盘素材",
    "web上传",
    "web_uploads",
    "training",
    "youth",
    "team",
    "tournament",
    "venue",
    "company",
    "l1",
    "l2",
    "l3",
    "l4",
}
DOMAIN_HINTS = (
    ("company", ("公司", "品牌", "资质", "简介", "介绍")),
    ("venue", ("场馆", "场地")),
    ("youth", ("青训", "选秀")),
    ("team", ("战队", "俱乐部", "选手")),
    ("tournament", ("赛事", "比赛", "联赛")),
    ("training", ("培训", "课程", "训练营", "教育")),
)
CONFIDENTIALITY_RANK = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}


class FileChangedDuringRead(RuntimeError):
    pass


def requires_ingestion_review(path_or_suffix: Path | str) -> bool:
    """Return whether a supported source must enter the human review queue."""
    value = str(path_or_suffix).lower()
    suffix = (
        value
        if value.startswith(".") and "/" not in value and "\\" not in value
        else Path(value).suffix
    )
    return suffix not in AUTO_APPROVED_ASSET_SUFFIXES


def _stat_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _assert_stable(
    path: Path,
    expected_stat: tuple[int, int] | None,
) -> None:
    if expected_stat is not None and _stat_signature(path) != expected_stat:
        raise FileChangedDuringRead("文件在读取期间发生变化，将在下次扫描重试")


def adopt_source(path: Path, content_hash: str) -> tuple[Path, bool]:
    if not settings.copy_sources:
        return path, False
    target_dir = settings.managed_source_dir / content_hash
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    if target.exists() and file_sha256(target) == content_hash:
        return target, False
    shutil.copy2(path, target)
    if file_sha256(target) != content_hash:
        target.unlink(missing_ok=True)
        raise IOError("受控副本哈希校验失败")
    return target, True


def _find_or_create_project(
    db: Session,
    *,
    name: str,
    client: str | None,
    year: int | None,
    domain: str,
    confidentiality: str,
    knowledge_status: str,
) -> Project:
    project = db.scalar(
        select(Project).where(
            Project.name == name,
            Project.year == year,
        )
    )
    if project:
        return project
    project = Project(
        name=name,
        client=client,
        year=year,
        domain=domain,
        confidentiality=confidentiality,
        knowledge_status=knowledge_status,
        confirmed=False,
    )
    db.add(project)
    db.flush()
    return project


def _duplicate_family(role: str) -> str:
    return "contract" if role == "contract" else "knowledge"


def _lock_duplicate_context(
    db: Session,
    *,
    content_hash: str,
    role: str,
    confidentiality: str,
) -> None:
    """Serialize identical imports across the Web and NAS ingest workers."""
    if db.get_bind().dialect.name != "postgresql":
        return
    context = (
        f"{content_hash}:{_duplicate_family(role)}:{confidentiality}"
    ).encode("utf-8")
    lock_key = int.from_bytes(
        hashlib.sha256(context).digest()[:8],
        byteorder="big",
        signed=True,
    )
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


def filter_exact_duplicate_documents(db: Session) -> int:
    """Hide byte-identical knowledge copies while preserving security contexts."""
    documents = db.scalars(
        select(Document)
        .where(Document.knowledge_status.in_(["candidate", "approved", "current"]))
        .order_by(Document.ingested_at.asc(), Document.id.asc())
    ).all()
    grouped: dict[tuple[str, str, str], list[Document]] = defaultdict(list)
    for document in documents:
        grouped[
            (
                document.content_hash,
                _duplicate_family(document.role),
                document.confidentiality,
            )
        ].append(document)

    status_priority = {"current": 0, "approved": 1, "candidate": 2}
    duplicate_ids: list[str] = []
    canonical_ids: list[str] = []
    for group in grouped.values():
        if len(group) < 2:
            continue
        ordered = sorted(
            group,
            key=lambda item: (
                status_priority.get(item.knowledge_status, 9),
                item.ingested_at,
                item.id,
            ),
        )
        canonical = ordered[0]
        changed_group = False
        for duplicate in ordered[1:]:
            if duplicate.knowledge_status not in {"candidate", "approved"}:
                continue
            duplicate.knowledge_status = "duplicate"
            duplicate_ids.append(duplicate.id)
            changed_group = True
        if changed_group:
            canonical_ids.append(canonical.id)

    if not duplicate_ids:
        return 0
    db.add(
        AuditLog(
            user_id=None,
            action="exact_duplicates_filtered",
            document_ids_json=json.dumps(duplicate_ids),
            details_json=json.dumps(
                {
                    "duplicate_count": len(duplicate_ids),
                    "canonical_document_ids": canonical_ids,
                    "rule": "sha256+security_context",
                    "source_files_deleted": False,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return len(duplicate_ids)


def ingest_document(
    db: Session,
    entry: dict,
    *,
    expected_stat: tuple[int, int] | None = None,
) -> dict:
    path = Path(entry["path"]).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    _assert_stable(path, expected_stat)
    content_hash = file_sha256(path)
    target_domain = entry.get("domain", "training")
    target_project_name = entry.get("project_name") or path.stem
    target_role = entry.get("role", "proposal")
    target_confidentiality = entry.get("confidentiality", "L3")
    _lock_duplicate_context(
        db,
        content_hash=content_hash,
        role=target_role,
        confidentiality=target_confidentiality,
    )
    review_required = bool(entry.get("force_review")) or requires_ingestion_review(path)
    _assert_stable(path, expected_stat)
    managed_path, source_adopted = adopt_source(path, content_hash)
    blob = db.get(FileBlob, content_hash)
    if not blob:
        blob = FileBlob(
            content_hash=content_hash,
            size_bytes=path.stat().st_size,
            source_path=str(managed_path),
        )
        db.add(blob)
        db.flush()
    elif managed_path.is_file() and (
        not Path(blob.source_path).is_file() or settings.copy_sources
    ):
        blob.source_path = str(managed_path)
        blob.size_bytes = managed_path.stat().st_size
    managed_stat = managed_path.stat()
    record_source_health(
        db,
        blob,
        {
            "status": "verified",
            "observed_size_bytes": managed_stat.st_size,
            "observed_mtime_ns": managed_stat.st_mtime_ns,
            "observed_hash": content_hash,
            "error_code": None,
        },
    )

    # Exact copies share one knowledge record across categories and projects.
    # Security contexts stay isolated so a public copy can never swallow a
    # contract, and a lower-classified copy can never swallow a higher one.
    family_filter = (
        Document.role == "contract"
        if target_role == "contract"
        else Document.role != "contract"
    )
    existing = db.scalar(
        select(Document)
        .where(
            Document.content_hash == content_hash,
            family_filter,
            Document.confidentiality == target_confidentiality,
            Document.knowledge_status.notin_(
                ["deleted", "quarantined", "rejected", "duplicate"]
            ),
        )
        .order_by(Document.ingested_at.asc(), Document.id.asc())
    )
    if existing:
        automatically_approved = (
            existing.knowledge_status == "candidate"
            and not review_required
        )
        if automatically_approved:
            existing.knowledge_status = "approved"
            db.add(
                AuditLog(
                    user_id=None,
                    action="asset_auto_approved",
                    document_ids_json=json.dumps([existing.id]),
                    details_json=json.dumps(
                        {
                            "suffix": path.suffix.lower(),
                            "previous_status": "candidate",
                            "knowledge_status": "approved",
                            "reason": "asset_format_exempt_from_review",
                        },
                        ensure_ascii=False,
                    ),
                )
            )
        _assert_stable(path, expected_stat)
        db.commit()
        return {
            "document_id": existing.id,
            "status": "unchanged",
            "title": existing.title,
            "knowledge_status": existing.knowledge_status,
            "review_required": review_required,
            "duplicate_filtered": True,
            "source_adopted": source_adopted,
            "source_available": True,
        }

    pages, citation_basis, page_count = parse_file(path)
    _assert_stable(path, expected_stat)
    requested_status = entry.get("knowledge_status", "candidate")
    knowledge_status = (
        "approved"
        if requested_status == "candidate" and not review_required
        else requested_status
    )
    project = _find_or_create_project(
        db,
        name=target_project_name,
        client=entry.get("client"),
        year=entry.get("year"),
        domain=target_domain,
        confidentiality=entry.get("confidentiality", "L3"),
        knowledge_status=knowledge_status,
    )
    document = Document(
        project_id=project.id,
        content_hash=content_hash,
        title=entry.get("title", path.name),
        role=target_role,
        version=entry.get("version", "未确认"),
        is_final=bool(entry.get("is_final", False)),
        knowledge_status=knowledge_status,
        confidentiality=entry.get("confidentiality", "L3"),
        page_count=page_count,
        citation_basis=citation_basis,
    )
    db.add(document)
    db.flush()
    chunk_index = 0
    for page, text, section in pages:
        for chunk in chunk_text(text):
            db.add(
                Chunk(
                    document_id=document.id,
                    page=page,
                    chunk_index=chunk_index,
                    section=section,
                    text=chunk,
                )
            )
            chunk_index += 1
    if knowledge_status == "approved" and requested_status == "candidate":
        db.add(
            AuditLog(
                user_id=None,
                action="asset_auto_approved",
                document_ids_json=json.dumps([document.id]),
                details_json=json.dumps(
                    {
                        "suffix": path.suffix.lower(),
                        "previous_status": "candidate",
                        "knowledge_status": "approved",
                        "reason": "asset_format_exempt_from_review",
                    },
                    ensure_ascii=False,
                ),
            )
        )
    db.commit()
    return {
        "document_id": document.id,
        "status": "ingested",
        "title": document.title,
        "pages": document.page_count,
        "chunks": chunk_index,
        "citation_basis": citation_basis,
        "knowledge_status": document.knowledge_status,
        "review_required": review_required,
        "duplicate_filtered": False,
        "source_adopted": source_adopted,
        "source_available": True,
    }


def auto_approve_pending_assets(db: Session) -> int:
    """Apply the current review policy to assets registered before this release."""
    candidates = db.scalars(
        select(Document).where(Document.knowledge_status == "candidate")
    ).all()
    approved_ids: list[str] = []
    suffix_counts: dict[str, int] = {}
    for document in candidates:
        if not document.file_blob:
            continue
        if document.role == "contract":
            continue
        suffix = Path(document.file_blob.source_path).suffix.lower()
        if requires_ingestion_review(suffix):
            continue
        document.knowledge_status = "approved"
        approved_ids.append(document.id)
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
    if not approved_ids:
        return 0
    db.add(
        AuditLog(
            user_id=None,
            action="asset_review_policy_backfill",
            document_ids_json=json.dumps(approved_ids),
            details_json=json.dumps(
                {
                    "count": len(approved_ids),
                    "suffix_counts": suffix_counts,
                    "previous_status": "candidate",
                    "knowledge_status": "approved",
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return len(approved_ids)


def _clean_folder_name(value: str) -> str:
    cleaned = re.sub(r"^\d{1,3}[_\-\s]+", "", value).strip()
    return cleaned or value


def _infer_domain(relative_path: Path) -> str:
    parts = [part.strip() for part in relative_path.parts]
    lowered = [part.lower() for part in parts]
    if "web上传" in lowered or "web_uploads" in lowered:
        # The Web uploader always writes <category-key>/<level>/Web上传/...
        # and validates the stable category key before creating this path.
        if parts and re.fullmatch(r"[A-Za-z0-9_]{1,40}", parts[0]):
            return parts[0].lower()
    for part in relative_path.parts:
        normalized = part.strip().lower()
        if normalized in {"training", "youth", "team", "tournament", "venue", "company"}:
            return normalized
    value = relative_path.as_posix().lower()
    for domain, hints in DOMAIN_HINTS:
        if any(hint in value for hint in hints):
            return domain
    return "training"


def _infer_role(relative_path: Path) -> str:
    value = relative_path.as_posix().lower()
    if any(hint in value for hint in ("公司介绍", "公司简介", "企业介绍")):
        return "company_profile"
    if any(hint in value for hint in ("brief", "需求书", "招标文件")):
        return "brief"
    if any(hint in value for hint in ("结案", "复盘", "验收", "总结报告")):
        return "closing_report"
    if any(hint in value for hint in ("执行", "排期", "活动情况", "实施")):
        return "execution"
    if relative_path.suffix.lower() in AUTO_APPROVED_ASSET_SUFFIXES:
        return "asset"
    return "proposal"


def _infer_project_name(relative_path: Path) -> str:
    if any(part.strip().lower() in {"web上传", "web_uploads"} for part in relative_path.parts):
        return _clean_folder_name(relative_path.stem)
    parent = relative_path.parent
    while parent != Path("."):
        name = _clean_folder_name(parent.name)
        if name.lower() not in GENERIC_FOLDERS and not re.fullmatch(
            r"20\d{2}",
            name,
        ):
            return name
        parent = parent.parent
    return _clean_folder_name(relative_path.stem)


def _infer_version(stem: str) -> str:
    matches = re.findall(
        r"(?i)(?:^|[_\-\s(（])v\d+(?:\.\d+){0,2}(?=$|[_\-\s)）])",
        stem,
    )
    if not matches:
        return "未确认"
    return matches[-1].strip("_- （(").lower()


def _infer_confidentiality(relative_path: Path) -> str:
    value = relative_path.as_posix().lower()
    for part in relative_path.parts:
        normalized = part.strip().lower()
        if normalized in {"l1", "l2", "l3", "l4"}:
            return normalized.upper()
    if any(
        hint in value
        for hint in ("人员评价", "人事", "身份证", "未成年人", "核心经营")
    ):
        return "L4"
    return "L3"


def prefill_entry(
    path: Path,
    inbox_root: Path,
    *,
    domain_override: str | None = None,
) -> dict:
    relative_path = path.relative_to(inbox_root)
    year_match = re.search(r"(?<!\d)(20\d{2})(?!\d)", relative_path.as_posix())
    return {
        "path": str(path),
        "title": path.name,
        "project_name": _infer_project_name(relative_path),
        "client": None,
        "year": int(year_match.group(1)) if year_match else None,
        "domain": domain_override or _infer_domain(relative_path),
        "role": _infer_role(relative_path),
        "version": _infer_version(path.stem),
        "is_final": False,
        "confidentiality": _infer_confidentiality(relative_path),
        "knowledge_status": (
            "candidate" if requires_ingestion_review(path) else "approved"
        ),
    }


def _issue_message(status: str, code: str, suffix: str = "") -> str:
    if code == "unsupported_type":
        return f"暂不支持的文件类型：{suffix or '无扩展名'}"
    if code == "file_too_large":
        return "文件超过当前单文件大小上限"
    if code == "still_uploading":
        return "文件可能仍在上传，将在下次扫描重试"
    if code == "path_escape":
        return "文件路径超出待审核目录，已拒绝读取"
    if code == "symlink_not_allowed":
        return "不读取符号链接"
    if code == "contract_layout_invalid":
        return "合同档案目录不符合固定分类与密级规则"
    return f"解析失败：{code}"


def _upsert_issue(
    db: Session,
    *,
    relative_path: str,
    status: str,
    error_code: str,
    message: str,
    size_bytes: int,
    modified_ns: int,
    now: datetime,
) -> None:
    issue = db.scalar(
        select(InboxIssue).where(InboxIssue.relative_path == relative_path)
    )
    if issue is None:
        issue = InboxIssue(
            relative_path=relative_path,
            status=status,
            error_code=error_code,
            message=message,
            size_bytes=size_bytes,
            modified_ns=modified_ns,
            first_seen_at=now,
        )
        db.add(issue)
    else:
        issue.status = status
        issue.error_code = error_code
        issue.message = message
        issue.size_bytes = size_bytes
        issue.modified_ns = modified_ns
        issue.resolved_at = None
    issue.last_seen_at = now
    db.commit()


def _resolve_issue(
    db: Session,
    relative_path: str,
    now: datetime,
) -> None:
    issue = db.scalar(
        select(InboxIssue).where(
            InboxIssue.relative_path == relative_path,
            InboxIssue.resolved_at.is_(None),
        )
    )
    if issue:
        issue.resolved_at = now
        issue.last_seen_at = now
        db.commit()


def scan_inbox(
    db: Session,
    inbox_root: Path | None = None,
    *,
    settle_seconds: int | None = None,
    max_file_bytes: int | None = None,
    now: datetime | None = None,
) -> dict:
    root = (inbox_root or settings.inbox_dir).resolve()
    settle = (
        settings.inbox_settle_seconds
        if settle_seconds is None
        else max(0, settle_seconds)
    )
    max_bytes = max_file_bytes or settings.inbox_max_file_bytes
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    started = time.perf_counter()
    counts = {
        "discovered": 0,
        "ingested": 0,
        "unchanged": 0,
        "deferred": 0,
        "unsupported": 0,
        "failed": 0,
        "skipped": 0,
    }
    results: list[dict] = []

    if not root.is_dir():
        counts["failed"] = 1
        status = "unavailable"
        db.add(
            AuditLog(
                user_id=None,
                action="inbox_scan",
                details_json=json.dumps(
                    {
                        "status": status,
                        "counts": counts,
                        "duration_ms": round(
                            (time.perf_counter() - started) * 1000,
                            2,
                        ),
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()
        return {
            "status": status,
            "counts": counts,
            "items": [],
            "checked_at": checked_at.isoformat(),
        }

    root_resolved = root.resolve()
    category_domains = {
        item.name.casefold(): item.key
        for item in db.scalars(
            select(KnowledgeCategory).where(KnowledgeCategory.active.is_(True))
        ).all()
    }
    seen_relative_paths: set[str] = set()
    successful_relative_paths: set[str] = set()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
        relative = path.relative_to(root)
        relative_value = relative.as_posix()
        if (
            relative.parts
            and relative.parts[0].strip().casefold()
            in SYSTEM_MANAGED_SCAN_EXCLUSION_KEYS
        ):
            if path.is_file():
                counts["skipped"] += 1
            continue
        if any(
            part.startswith(".") or part.startswith("~$")
            for part in relative.parts
        ) or (
            path.suffix.lower() in TEMPORARY_SUFFIXES
            or TEMPORARY_NAME_RE.search(path.name)
        ):
            counts["skipped"] += 1
            continue
        if path.is_symlink():
            counts["discovered"] += 1
            counts["failed"] += 1
            seen_relative_paths.add(relative_value)
            stat = path.lstat()
            _upsert_issue(
                db,
                relative_path=relative_value,
                status="failed",
                error_code="symlink_not_allowed",
                message=_issue_message("failed", "symlink_not_allowed"),
                size_bytes=stat.st_size,
                modified_ns=stat.st_mtime_ns,
                now=checked_at,
            )
            results.append({
                "relative_path": relative_value,
                "status": "failed",
                "error_code": "symlink_not_allowed",
            })
            continue
        if not path.is_file():
            continue

        counts["discovered"] += 1
        seen_relative_paths.add(relative_value)
        stat = path.stat()
        contract_category = None
        if is_contract_archive_path(relative):
            try:
                contract_category = contract_category_for_path(relative)
            except ValueError:
                counts["failed"] += 1
                _upsert_issue(
                    db,
                    relative_path=relative_value,
                    status="failed",
                    error_code="contract_layout_invalid",
                    message=_issue_message("failed", "contract_layout_invalid"),
                    size_bytes=stat.st_size,
                    modified_ns=stat.st_mtime_ns,
                    now=checked_at,
                )
                results.append({
                    "relative_path": relative_value,
                    "status": "failed",
                    "error_code": "contract_layout_invalid",
                })
                continue
        try:
            resolved = path.resolve()
            resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            counts["failed"] += 1
            _upsert_issue(
                db,
                relative_path=relative_value,
                status="failed",
                error_code="path_escape",
                message=_issue_message("failed", "path_escape"),
                size_bytes=stat.st_size,
                modified_ns=stat.st_mtime_ns,
                now=checked_at,
            )
            results.append({
                "relative_path": relative_value,
                "status": "failed",
                "error_code": "path_escape",
            })
            continue

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            counts["unsupported"] += 1
            _upsert_issue(
                db,
                relative_path=relative_value,
                status="unsupported",
                error_code="unsupported_type",
                message=_issue_message(
                    "unsupported",
                    "unsupported_type",
                    suffix,
                ),
                size_bytes=stat.st_size,
                modified_ns=stat.st_mtime_ns,
                now=checked_at,
            )
            results.append({
                "relative_path": relative_value,
                "status": "unsupported",
                "error_code": "unsupported_type",
            })
            continue
        if stat.st_size > max_bytes:
            counts["failed"] += 1
            _upsert_issue(
                db,
                relative_path=relative_value,
                status="failed",
                error_code="file_too_large",
                message=_issue_message("failed", "file_too_large"),
                size_bytes=stat.st_size,
                modified_ns=stat.st_mtime_ns,
                now=checked_at,
            )
            results.append({
                "relative_path": relative_value,
                "status": "failed",
                "error_code": "file_too_large",
            })
            continue
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        if (checked_at - modified_at).total_seconds() < settle:
            counts["deferred"] += 1
            _upsert_issue(
                db,
                relative_path=relative_value,
                status="deferred",
                error_code="still_uploading",
                message=_issue_message("deferred", "still_uploading"),
                size_bytes=stat.st_size,
                modified_ns=stat.st_mtime_ns,
                now=checked_at,
            )
            results.append({
                "relative_path": relative_value,
                "status": "deferred",
                "error_code": "still_uploading",
            })
            continue

        try:
            category_domain = (
                category_domains.get(relative.parts[0].casefold())
                if relative.parts
                else None
            )
            entry = prefill_entry(
                path,
                root,
                domain_override=(
                    contract_category.domain
                    if contract_category
                    else category_domain
                ),
            )
            if contract_category:
                entry.update(
                    {
                        "project_name": (
                            f"{contract_category.name} · {path.stem}"
                        ),
                        "role": "contract",
                        "confidentiality": contract_category.confidentiality,
                        "knowledge_status": "candidate",
                        "force_review": True,
                    }
                )
            result = ingest_document(
                db,
                entry,
                expected_stat=(stat.st_size, stat.st_mtime_ns),
            )
            item_status = result["status"]
            counts[item_status] += 1
            successful_relative_paths.add(relative_value)
            _resolve_issue(db, relative_value, checked_at)
            results.append({
                "relative_path": relative_value,
                "status": item_status,
                "document_id": result["document_id"],
            })
        except Exception as exc:
            db.rollback()
            counts["failed"] += 1
            error_code = type(exc).__name__
            _upsert_issue(
                db,
                relative_path=relative_value,
                status="failed",
                error_code=error_code[:80],
                message=_issue_message("failed", error_code)[:300],
                size_bytes=stat.st_size,
                modified_ns=stat.st_mtime_ns,
                now=checked_at,
            )
            results.append({
                "relative_path": relative_value,
                "status": "failed",
                "error_code": error_code,
            })

    open_issues = db.scalars(
        select(InboxIssue).where(InboxIssue.resolved_at.is_(None))
    ).all()
    for issue in open_issues:
        if (
            issue.relative_path not in seen_relative_paths
            or issue.relative_path in successful_relative_paths
        ):
            issue.resolved_at = checked_at
            issue.last_seen_at = checked_at

    status = (
        "warning"
        if counts["failed"] or counts["unsupported"]
        else "ok"
    )
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    db.add(
        AuditLog(
            user_id=None,
            action="inbox_scan",
            details_json=json.dumps(
                {
                    "status": status,
                    "counts": counts,
                    "duration_ms": duration_ms,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    return {
        "status": status,
        "counts": counts,
        "items": results,
        "duration_ms": duration_ms,
        "checked_at": checked_at.isoformat(),
    }


def ingest_manifest(db: Session, manifest_path: Path) -> list[dict]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload["documents"] if isinstance(payload, dict) else payload
    results: list[dict] = []
    for entry in entries:
        try:
            results.append(ingest_document(db, entry))
        except Exception as exc:  # CLI must report the remaining files too.
            db.rollback()
            results.append(
                {
                    "status": "failed",
                    "title": entry.get("title") or Path(entry["path"]).name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return results
