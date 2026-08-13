from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from .config import AGENT_ROOT, settings
from .models import (
    AuditLog,
    Chunk,
    ChunkEmbedding,
    Document,
    DocumentArtifact,
    EvolutionCandidateRecord,
    EvolutionChangePlan,
    EvolutionReviewRun,
    FileBlob,
    InboxIssue,
    KnowledgeCategory,
    MaintainedArtifact,
    Project,
    ProjectKnowledgeCard,
    ReviewProposal,
    SourceHealth,
    User,
    WritingDraft,
)
BACKUP_SCHEMA_VERSION = 1


class BackupError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _copy_tree(source: Path, target: Path) -> None:
    if not source.is_dir():
        return
    for item in source.rglob("*"):
        if item.is_symlink():
            raise BackupError(f"symlink_not_allowed:{item.name}")
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)


def _copy_content_addressed_sources(
    blobs: list[FileBlob],
    target: Path,
) -> set[str]:
    copied_hashes: set[str] = set()
    for blob in blobs:
        content_hash = blob.content_hash.upper()
        if len(content_hash) != 64 or any(
            character not in "0123456789ABCDEF" for character in content_hash
        ):
            raise BackupError("invalid_source_content_hash")
        source = Path(blob.source_path)
        if source.is_symlink():
            raise BackupError(f"symlink_not_allowed:{source.name}")
        try:
            if not source.is_file() or file_sha256(source) != content_hash:
                continue
        except OSError:
            continue
        suffix = source.suffix.lower() or ".bin"
        destination = target / content_hash / f"source{suffix}"
        if not _inside(destination, target):
            raise BackupError("backup_source_target_outside_root")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if file_sha256(destination) != content_hash:
                raise BackupError(f"backup_source_collision:{content_hash}")
            copied_hashes.add(content_hash)
            continue
        shutil.copy2(source, destination)
        if file_sha256(destination) != content_hash:
            raise BackupError(f"backup_source_copy_mismatch:{content_hash}")
        copied_hashes.add(content_hash)
    return copied_hashes


def _sqlite_snapshot(database_path: Path, destination: Path) -> None:
    if not database_path.is_file():
        raise BackupError("sqlite_database_missing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(
        f"file:{database_path.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    target_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(target_connection)
        result = target_connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise BackupError("sqlite_integrity_check_failed")
    finally:
        target_connection.close()
        source_connection.close()


def _postgres_snapshot(destination: Path) -> None:
    url = make_url(settings.database_url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--file",
        str(destination),
    ]
    if url.host:
        command.extend(["--host", url.host])
    if url.port:
        command.extend(["--port", str(url.port)])
    if url.username:
        command.extend(["--username", url.username])
    command.append(url.database or "jingao")
    try:
        subprocess.run(
            command,
            check=True,
            timeout=600,
            env=environment,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise BackupError("pg_dump_not_installed") from exc
    except subprocess.CalledProcessError as exc:
        raise BackupError("pg_dump_failed") from exc


def _database_counts(db: Session) -> dict[str, int]:
    return {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "knowledge_categories": (
            db.scalar(select(func.count(KnowledgeCategory.id))) or 0
        ),
        "projects": db.scalar(select(func.count(Project.id))) or 0,
        "project_knowledge_cards": (
            db.scalar(select(func.count(ProjectKnowledgeCard.id))) or 0
        ),
        "file_blobs": db.scalar(select(func.count(FileBlob.content_hash))) or 0,
        "documents": db.scalar(select(func.count(Document.id))) or 0,
        "chunks": db.scalar(select(func.count(Chunk.id))) or 0,
        "embeddings": db.scalar(select(func.count(ChunkEmbedding.id))) or 0,
        "document_artifacts": (
            db.scalar(select(func.count(DocumentArtifact.id))) or 0
        ),
        "review_proposals": (
            db.scalar(select(func.count(ReviewProposal.id))) or 0
        ),
        "writing_drafts": (
            db.scalar(select(func.count(WritingDraft.id))) or 0
        ),
        "maintained_artifacts": (
            db.scalar(select(func.count(MaintainedArtifact.id))) or 0
        ),
        "evolution_review_runs": (
            db.scalar(select(func.count(EvolutionReviewRun.id))) or 0
        ),
        "evolution_candidate_records": (
            db.scalar(select(func.count(EvolutionCandidateRecord.id))) or 0
        ),
        "evolution_change_plans": (
            db.scalar(select(func.count(EvolutionChangePlan.id))) or 0
        ),
        "inbox_issues": db.scalar(select(func.count(InboxIssue.id))) or 0,
        "source_health": (
            db.scalar(select(func.count(SourceHealth.content_hash))) or 0
        ),
        "audit_logs": db.scalar(select(func.count(AuditLog.id))) or 0,
    }


def _manifest_files(package: Path) -> list[dict]:
    files: list[dict] = []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.name in {"manifest.json", "COMPLETE"}:
            continue
        files.append(
            {
                "path": path.relative_to(package).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return files


def create_backup(db: Session, output_root: Path | None = None) -> dict:
    backup_root = (
        output_root
        or Path(os.getenv("JINGAO_BACKUP_DIR", AGENT_ROOT / "backups"))
    ).resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    final = backup_root / f"jingao-{timestamp}-{suffix}"
    incomplete = backup_root / f".incomplete-{timestamp}-{suffix}"
    if not _inside(incomplete, backup_root) or not _inside(final, backup_root):
        raise BackupError("backup_target_outside_root")
    incomplete.mkdir(parents=False, exist_ok=False)
    try:
        url = make_url(settings.database_url)
        if url.get_backend_name() == "sqlite":
            database_name = "database.sqlite3"
            database_path = Path(url.database or "").resolve()
            _sqlite_snapshot(database_path, incomplete / database_name)
            database_engine = "sqlite"
        elif url.get_backend_name() == "postgresql":
            database_name = "database.dump"
            _postgres_snapshot(incomplete / database_name)
            database_engine = "postgresql"
        else:
            raise BackupError("database_engine_unsupported")

        blobs = db.scalars(select(FileBlob)).all()
        _copy_tree(settings.managed_source_dir, incomplete / "sources")
        copied_source_hashes = _copy_content_addressed_sources(
            blobs,
            incomplete / "sources",
        )
        _copy_tree(settings.data_dir / "derived", incomplete / "derived")
        _copy_tree(settings.evaluation_dir, incomplete / "evaluations")
        available_hashes = sorted(copied_source_hashes)
        all_source_hashes = {row.content_hash for row in blobs}
        manifest = {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database_engine": database_engine,
            "database_file": database_name,
            "policy_version": settings.policy_version,
            "counts": _database_counts(db),
            "source_content_hashes_available": available_hashes,
            "source_content_hashes_missing": sorted(
                all_source_hashes - copied_source_hashes
            ),
            "files": _manifest_files(incomplete),
        }
        manifest_path = incomplete / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest_hash = file_sha256(manifest_path)
        complete_payload = json.dumps(
            {
                "manifest_sha256": manifest_hash,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        )
        try:
            incomplete.replace(final)
        except PermissionError:
            # Some managed Windows folders deny directory rename even though
            # individual file moves are allowed. COMPLETE is deliberately
            # written only after every file has arrived, so partial copies are
            # never accepted by the verifier.
            final.mkdir(parents=False, exist_ok=False)
            for item in list(incomplete.iterdir()):
                shutil.move(str(item), str(final / item.name))
            incomplete.rmdir()
        (final / "COMPLETE").write_text(
            complete_payload,
            encoding="utf-8",
        )
        return {
            "status": "ready",
            "path": str(final),
            "database_engine": database_engine,
            "counts": manifest["counts"],
            "file_count": len(manifest["files"]),
            "total_bytes": sum(item["size_bytes"] for item in manifest["files"]),
            "manifest_sha256": manifest_hash,
        }
    except Exception:
        if incomplete.exists() and _inside(incomplete, backup_root):
            shutil.rmtree(incomplete)
        if (
            final.exists()
            and _inside(final, backup_root)
            and not (final / "COMPLETE").exists()
        ):
            shutil.rmtree(final)
        raise


def _load_and_verify_manifest(package: Path) -> dict:
    package = package.resolve()
    manifest_path = package / "manifest.json"
    complete_path = package / "COMPLETE"
    if not manifest_path.is_file() or not complete_path.is_file():
        raise BackupError("backup_incomplete")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        complete = json.loads(complete_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BackupError("backup_metadata_invalid") from exc
    if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise BackupError("backup_schema_unsupported")
    if complete.get("manifest_sha256") != file_sha256(manifest_path):
        raise BackupError("manifest_hash_mismatch")
    for item in manifest.get("files", []):
        relative = Path(item["path"])
        path = (package / relative).resolve()
        if not _inside(path, package) or not path.is_file():
            raise BackupError(f"backup_file_missing:{relative.as_posix()}")
        if path.stat().st_size != item["size_bytes"]:
            raise BackupError(f"backup_size_mismatch:{relative.as_posix()}")
        if file_sha256(path) != item["sha256"]:
            raise BackupError(f"backup_hash_mismatch:{relative.as_posix()}")
    return manifest


def _sqlite_counts(database_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(
        f"file:{database_path.as_posix()}?mode=ro",
        uri=True,
    )
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise BackupError("sqlite_integrity_check_failed")
        table_map = {
            "users": "users",
            "knowledge_categories": "knowledge_categories",
            "projects": "projects",
            "project_knowledge_cards": "project_knowledge_cards",
            "file_blobs": "file_blobs",
            "documents": "documents",
            "chunks": "chunks",
            "embeddings": "chunk_embeddings",
            "document_artifacts": "document_artifacts",
            "review_proposals": "review_proposals",
            "writing_drafts": "writing_drafts",
            "maintained_artifacts": "maintained_artifacts",
            "evolution_review_runs": "evolution_review_runs",
            "evolution_candidate_records": "evolution_candidate_records",
            "evolution_change_plans": "evolution_change_plans",
            "inbox_issues": "inbox_issues",
            "source_health": "source_health",
            "audit_logs": "audit_logs",
        }
        existing_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        return {
            name: int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
            )
            for name, table in table_map.items()
            if table in existing_tables
        }
    finally:
        connection.close()


def verify_backup(package: Path) -> dict:
    package = package.resolve()
    manifest = _load_and_verify_manifest(package)
    database_path = package / manifest["database_file"]
    if manifest["database_engine"] == "sqlite":
        raw_counts = _sqlite_counts(database_path)
        counts = {
            name: raw_counts[name] for name in manifest["counts"]
        }
        if counts != manifest["counts"]:
            raise BackupError("database_count_mismatch")
    elif manifest["database_engine"] == "postgresql":
        try:
            subprocess.run(
                ["pg_restore", "--list", str(database_path)],
                check=True,
                timeout=120,
                capture_output=True,
            )
        except FileNotFoundError as exc:
            raise BackupError("pg_restore_not_installed") from exc
        except subprocess.CalledProcessError as exc:
            raise BackupError("postgres_archive_invalid") from exc
        counts = manifest["counts"]
    else:
        raise BackupError("database_engine_unsupported")

    source_verified = 0
    for content_hash in manifest["source_content_hashes_available"]:
        source_dir = package / "sources" / content_hash
        candidates = [path for path in source_dir.rglob("*") if path.is_file()]
        if not candidates or not any(
            file_sha256(path) == content_hash for path in candidates
        ):
            raise BackupError(f"source_hash_missing:{content_hash}")
        source_verified += 1
    return {
        "status": "verified",
        "path": str(package),
        "database_engine": manifest["database_engine"],
        "counts": counts,
        "file_count": len(manifest["files"]),
        "source_files_verified": source_verified,
        "source_files_missing_at_backup": len(
            manifest["source_content_hashes_missing"]
        ),
    }


def restore_sqlite_backup(package: Path, target_data_dir: Path) -> dict:
    package = package.resolve()
    target = target_data_dir.resolve()
    manifest = _load_and_verify_manifest(package)
    if manifest["database_engine"] != "sqlite":
        raise BackupError("restore_sqlite_requires_sqlite_backup")
    if target.exists() and any(target.iterdir()):
        raise BackupError("restore_target_not_empty")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(package / manifest["database_file"], target / "jingao.db")
    _copy_tree(package / "sources", target / "sources")
    _copy_tree(package / "derived", target / "derived")
    _copy_tree(package / "evaluations", target / "evaluations")

    database_path = target / "jingao.db"
    connection = sqlite3.connect(database_path)
    try:
        blobs = connection.execute(
            "SELECT content_hash FROM file_blobs"
        ).fetchall()
        for (content_hash,) in blobs:
            source_dir = target / "sources" / content_hash
            candidates = [path for path in source_dir.rglob("*") if path.is_file()]
            source_path = (
                candidates[0]
                if candidates
                else target / "missing_sources" / content_hash
            )
            connection.execute(
                "UPDATE file_blobs SET source_path = ? WHERE content_hash = ?",
                (str(source_path), content_hash),
            )
        artifacts = connection.execute(
            """
            SELECT document_artifacts.id, documents.content_hash
            FROM document_artifacts
            JOIN documents ON documents.id = document_artifacts.document_id
            WHERE document_artifacts.kind = 'reference_pdf'
              AND document_artifacts.status = 'ready'
            """
        ).fetchall()
        for artifact_id, content_hash in artifacts:
            reference = target / "derived" / content_hash / "reference.pdf"
            connection.execute(
                "UPDATE document_artifacts SET path = ? WHERE id = ?",
                (str(reference), artifact_id),
            )
        # Session tokens are deliberately ephemeral. A restored system always
        # requires every user to authenticate again.
        sessions_invalidated = connection.execute(
            "SELECT COUNT(*) FROM session_tokens"
        ).fetchone()[0]
        connection.execute("DELETE FROM session_tokens")
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise BackupError("restored_sqlite_integrity_check_failed")
    finally:
        connection.close()
    verification = verify_backup(package)
    reference_previews_verified = _verify_restored_references(database_path)
    return {
        "status": "restored",
        "target_data_dir": str(target),
        "counts": verification["counts"],
        "source_files_verified": verification["source_files_verified"],
        "reference_previews_verified": reference_previews_verified,
        "sessions_invalidated": sessions_invalidated,
    }


def _verify_restored_references(database_path: Path) -> int:
    import pymupdf

    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            """
            SELECT path, content_hash, page_count
            FROM document_artifacts
            WHERE kind = 'reference_pdf' AND status = 'ready'
            """
        ).fetchall()
    finally:
        connection.close()
    verified = 0
    for raw_path, expected_hash, expected_pages in rows:
        path = Path(raw_path)
        if not path.is_file():
            raise BackupError("restored_reference_missing")
        if expected_hash and file_sha256(path) != expected_hash:
            raise BackupError("restored_reference_hash_mismatch")
        try:
            with pymupdf.open(path) as pdf:
                if len(pdf) != expected_pages or len(pdf) < 1:
                    raise BackupError("restored_reference_page_mismatch")
                pdf[0].get_text()
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError("restored_reference_unreadable") from exc
        verified += 1
    return verified


def isolated_restore_check(package: Path) -> dict:
    with tempfile.TemporaryDirectory(
        prefix="jingao-restore-check-",
        dir=settings.data_dir,
    ) as temporary:
        result = restore_sqlite_backup(package, Path(temporary) / "data")
        restored_database = Path(result["target_data_dir"]) / "jingao.db"
        counts = _sqlite_counts(restored_database)
        return {
            "status": "restore_verified",
            "counts": counts,
            "source_files_verified": result["source_files_verified"],
            "reference_previews_verified": result[
                "reference_previews_verified"
            ],
            "sessions_invalidated": result["sessions_invalidated"],
        }
