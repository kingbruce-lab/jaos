from __future__ import annotations

import json
import os
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .models import AuditLog, Document, FileBlob, KnowledgeCategory
from .source_integrity import file_sha256


CONFIDENTIALITY_LEVELS = ("L1", "L2", "L3", "L4", "L5")
RESERVED_CATEGORY_FOLDERS = {"99_ai入库待审核", ".", ".."}
INVALID_FOLDER_CHARACTERS = re.compile(r"[\x00-\x1f<>:\"/\\|?*]")


class StorageLayoutError(RuntimeError):
    pass


def validate_category_folder_name(value: str) -> str:
    name = value.strip()
    if (
        not name
        or name.casefold() in RESERVED_CATEGORY_FOLDERS
        or name.endswith((" ", "."))
        or INVALID_FOLDER_CHARACTERS.search(name)
    ):
        raise StorageLayoutError(
            "资料分类名称不能包含路径符号、系统保留名称或结尾空格"
        )
    return name


def category_directory(knowledge_root: Path, category_name: str) -> Path:
    root = knowledge_root.resolve()
    target = (root / validate_category_folder_name(category_name)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise StorageLayoutError("资料分类目录超出知识库范围") from exc
    return target


def ensure_category_layout(knowledge_root: Path, category_name: str) -> Path:
    target = category_directory(knowledge_root, category_name)
    for level in CONFIDENTIALITY_LEVELS:
        (target / level).mkdir(parents=True, exist_ok=True)
    return target


def rename_category_layout(
    db: Session,
    knowledge_root: Path,
    old_name: str,
    new_name: str,
) -> int:
    old_directory = category_directory(knowledge_root, old_name)
    new_directory = category_directory(knowledge_root, new_name)
    if old_directory == new_directory:
        ensure_category_layout(knowledge_root, new_name)
        return 0
    if new_directory.exists():
        raise StorageLayoutError("新分类名称对应的 NAS 文件夹已经存在")

    updated_paths = 0
    if old_directory.exists():
        old_directory.rename(new_directory)
        for blob in db.scalars(select(FileBlob)).all():
            source = Path(blob.source_path)
            try:
                relative = source.relative_to(old_directory)
            except ValueError:
                continue
            blob.source_path = str(new_directory / relative)
            updated_paths += 1
    ensure_category_layout(knowledge_root, new_name)
    return updated_paths


def _unique_target(target: Path, content_hash: str) -> Path:
    if not target.exists():
        return target
    if target.is_file() and file_sha256(target) == content_hash:
        return target
    stem = target.stem
    suffix = target.suffix
    for length in (8, 12, 16, 24, 32):
        candidate = target.with_name(f"{stem}_{content_hash[:length]}{suffix}")
        if not candidate.exists():
            return candidate
        if candidate.is_file() and file_sha256(candidate) == content_hash:
            return candidate
    raise StorageLayoutError(f"无法为同名文件生成安全目标名称：{target.name}")


def _is_web_upload_path(path: Path) -> bool:
    return any(part.casefold() in {"web上传", "web_uploads"} for part in path.parts)


def _remove_empty_tree(root: Path) -> None:
    if not root.is_dir():
        return
    for current, _directories, _files in os.walk(root, topdown=False):
        path = Path(current)
        try:
            path.rmdir()
        except OSError:
            pass


def normalize_web_upload_storage(
    db: Session,
    knowledge_root: Path,
    inbox_root: Path,
    *,
    apply_changes: bool,
) -> dict:
    root = knowledge_root.resolve()
    inbox = inbox_root.resolve()
    categories = {
        item.key: item
        for item in db.scalars(select(KnowledgeCategory)).all()
    }
    if apply_changes:
        for category in categories.values():
            ensure_category_layout(root, category.name)

    rows = db.execute(
        select(Document)
        .options(
            joinedload(Document.project),
            joinedload(Document.file_blob),
        )
    ).unique().scalars().all()
    plans: list[tuple[Document, Path, Path]] = []
    missing = 0
    skipped = 0
    for document in rows:
        if not document.file_blob:
            continue
        source = Path(document.file_blob.source_path).resolve()
        if not _is_web_upload_path(source):
            continue
        try:
            source.relative_to(root)
        except ValueError:
            skipped += 1
            continue
        category = categories.get(document.project.domain)
        if category is None or document.confidentiality not in CONFIDENTIALITY_LEVELS:
            skipped += 1
            continue
        if not source.is_file():
            missing += 1
            continue
        target_directory = category_directory(root, category.name) / document.confidentiality
        target = _unique_target(
            target_directory / source.name,
            document.content_hash,
        )
        plans.append((document, source, target))

    category_counts: dict[str, int] = {}
    moved = 0
    reused = 0
    if apply_changes:
        for document, source, target in plans:
            if file_sha256(source) != document.content_hash:
                raise StorageLayoutError(f"迁移前哈希校验失败：{source.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if file_sha256(target) != document.content_hash:
                    raise StorageLayoutError(f"目标文件冲突：{target.name}")
                reused += 1
            else:
                source.rename(target)
                moved += 1
            document.file_blob.source_path = str(target)
            category = categories[document.project.domain]
            category_counts[category.name] = category_counts.get(category.name, 0) + 1

        for category in categories.values():
            old_key_directory = inbox / category.key
            try:
                old_key_directory.resolve().relative_to(inbox)
            except ValueError:
                continue
            _remove_empty_tree(old_key_directory)

        db.add(
            AuditLog(
                user_id=None,
                action="normalize_web_upload_storage",
                document_ids_json=json.dumps(
                    [document.id for document, _source, _target in plans]
                ),
                details_json=json.dumps(
                    {
                        "moved": moved,
                        "reused": reused,
                        "missing": missing,
                        "skipped": skipped,
                        "category_counts": category_counts,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()

    return {
        "status": "applied" if apply_changes else "dry_run",
        "planned": len(plans),
        "moved": moved,
        "reused": reused,
        "missing": missing,
        "skipped": skipped,
        "categories": category_counts if apply_changes else sorted({
            categories[document.project.domain].name
            for document, _source, _target in plans
        }),
    }


def normalize_inbox_storage(
    db: Session,
    knowledge_root: Path,
    inbox_root: Path,
    *,
    apply_changes: bool,
) -> dict:
    root = knowledge_root.resolve()
    inbox = inbox_root.resolve()
    categories = {
        item.key: item
        for item in db.scalars(select(KnowledgeCategory)).all()
    }
    company_category = categories.get("company")
    if apply_changes:
        for category in categories.values():
            ensure_category_layout(root, category.name)

    documents = db.execute(
        select(Document)
        .options(
            joinedload(Document.project),
            joinedload(Document.file_blob),
        )
    ).unique().scalars().all()
    document_by_path = {
        Path(item.file_blob.source_path).resolve(): item
        for item in documents
        if item.file_blob
    }
    document_by_hash = {
        item.content_hash: item
        for item in documents
    }
    plans: list[tuple[Path, Path, Document, str, bool]] = []
    planned_targets: dict[Path, str] = {}
    metadata_files: list[Path] = []
    skipped: list[Path] = []
    synthetic_count = 0

    for source in sorted(
        (item.resolve() for item in inbox.rglob("*") if item.is_file()),
        key=str,
    ):
        if source.name == ".DS_Store":
            metadata_files.append(source)
            continue
        relative = source.relative_to(inbox)
        registered_document = document_by_path.get(source)
        content_hash = (
            registered_document.content_hash
            if registered_document
            else file_sha256(source)
        )
        document = registered_document or document_by_hash.get(content_hash)
        if document is None or not document.project:
            skipped.append(source)
            continue

        is_synthetic = source.name.startswith("synthetic-ingest-")
        if is_synthetic:
            if company_category is None:
                skipped.append(source)
                continue
            category = company_category
            confidentiality = "L1"
            routed_relative = Path("系统测试归档") / source.name
            synthetic_count += 1
        else:
            category = categories.get(document.project.domain)
            confidentiality = document.confidentiality
            routed_relative = (
                Path(*relative.parts[1:])
                if len(relative.parts) > 1
                else relative
            )
        if category is None or confidentiality not in CONFIDENTIALITY_LEVELS:
            skipped.append(source)
            continue

        target = _unique_target(
            category_directory(root, category.name)
            / confidentiality
            / routed_relative,
            content_hash,
        )
        if target in planned_targets and planned_targets[target] != content_hash:
            target = target.with_name(
                f"{target.stem}_{content_hash[:12]}{target.suffix}"
            )
        planned_targets[target] = content_hash
        plans.append(
            (source, target, document, content_hash, is_synthetic)
        )

    moved = 0
    deduplicated = 0
    metadata_removed = 0
    updated_blob_paths = 0
    category_counts: dict[str, int] = {}
    if apply_changes:
        for source, target, document, content_hash, is_synthetic in plans:
            if file_sha256(source) != content_hash:
                raise StorageLayoutError(f"迁移前哈希校验失败：{source.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if file_sha256(target) != content_hash:
                    raise StorageLayoutError(f"目标文件冲突：{target.name}")
                source.unlink()
                deduplicated += 1
            else:
                source.rename(target)
                moved += 1
            if (
                document.file_blob
                and Path(document.file_blob.source_path).resolve() == source
            ):
                document.file_blob.source_path = str(target)
                updated_blob_paths += 1
            if is_synthetic:
                document.project.domain = "company"
                document.project.confidentiality = "L1"
                document.project.knowledge_status = "archived"
                document.confidentiality = "L1"
                document.knowledge_status = "archived"
            category_name = target.relative_to(root).parts[0]
            category_counts[category_name] = category_counts.get(category_name, 0) + 1

        for metadata in metadata_files:
            metadata.unlink(missing_ok=True)
            metadata_removed += 1
        for child in list(inbox.iterdir()):
            if child.is_dir():
                _remove_empty_tree(child)

        db.add(
            AuditLog(
                user_id=None,
                action="normalize_inbox_storage",
                document_ids_json=json.dumps(
                    list(dict.fromkeys(
                        document.id
                        for _source, _target, document, _hash, _synthetic in plans
                    ))
                ),
                details_json=json.dumps(
                    {
                        "moved": moved,
                        "deduplicated": deduplicated,
                        "metadata_removed": metadata_removed,
                        "updated_blob_paths": updated_blob_paths,
                        "skipped": len(skipped),
                        "synthetic_archived": synthetic_count,
                        "category_counts": category_counts,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.commit()

    return {
        "status": "applied" if apply_changes else "dry_run",
        "planned": len(plans),
        "moved": moved,
        "deduplicated": deduplicated,
        "metadata_files": len(metadata_files),
        "metadata_removed": metadata_removed,
        "updated_blob_paths": updated_blob_paths,
        "skipped": len(skipped),
        "synthetic_archived": synthetic_count,
        "categories": category_counts if apply_changes else sorted({
            target.relative_to(root).parts[0]
            for _source, target, _document, _hash, _synthetic in plans
        }),
    }
