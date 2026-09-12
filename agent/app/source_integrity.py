from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .models import AuditLog, FileBlob, SourceHealth


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
TEMPORARY_SUFFIXES = {".tmp", ".part", ".crdownload", ".download"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest().upper()


def source_is_available(
    blob: FileBlob | None,
    health: SourceHealth | None = None,
) -> bool:
    if blob is None:
        return False
    path = Path(blob.source_path)
    try:
        stat = path.stat()
    except OSError:
        return False
    if not path.is_file() or stat.st_size != blob.size_bytes:
        return False
    if health is None:
        # Legacy rows remain readable until the first integrity sweep.
        return True
    return (
        health.status == "verified"
        and health.observed_size_bytes == stat.st_size
        and health.observed_mtime_ns == stat.st_mtime_ns
        and health.observed_hash == blob.content_hash
    )


def verify_blob(blob: FileBlob) -> dict:
    path = Path(blob.source_path)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {
            "status": "missing",
            "observed_size_bytes": None,
            "observed_mtime_ns": None,
            "observed_hash": None,
            "error_code": "source_missing",
        }
    except OSError as exc:
        return {
            "status": "failed",
            "observed_size_bytes": None,
            "observed_mtime_ns": None,
            "observed_hash": None,
            "error_code": type(exc).__name__[:80],
        }
    if not path.is_file():
        return {
            "status": "missing",
            "observed_size_bytes": None,
            "observed_mtime_ns": None,
            "observed_hash": None,
            "error_code": "source_not_file",
        }
    try:
        observed_hash = file_sha256(path)
    except OSError as exc:
        return {
            "status": "failed",
            "observed_size_bytes": stat.st_size,
            "observed_mtime_ns": stat.st_mtime_ns,
            "observed_hash": None,
            "error_code": type(exc).__name__[:80],
        }
    verified = (
        stat.st_size == blob.size_bytes
        and observed_hash == blob.content_hash
    )
    return {
        "status": "verified" if verified else "mismatch",
        "observed_size_bytes": stat.st_size,
        "observed_mtime_ns": stat.st_mtime_ns,
        "observed_hash": observed_hash,
        "error_code": None if verified else "content_hash_mismatch",
    }


def record_source_health(
    db: Session,
    blob: FileBlob,
    observation: dict,
    *,
    now: datetime | None = None,
) -> SourceHealth:
    checked_at = now or datetime.now(timezone.utc)
    health = db.get(SourceHealth, blob.content_hash)
    if health is None:
        health = SourceHealth(content_hash=blob.content_hash)
        db.add(health)
    health.status = observation["status"]
    health.observed_size_bytes = observation.get("observed_size_bytes")
    health.observed_mtime_ns = observation.get("observed_mtime_ns")
    health.observed_hash = observation.get("observed_hash")
    health.error_code = observation.get("error_code")
    health.checked_at = checked_at
    if observation["status"] == "verified":
        health.verified_at = checked_at
    return health


def verify_and_record(
    db: Session,
    blob: FileBlob,
    *,
    now: datetime | None = None,
    commit: bool = True,
) -> SourceHealth:
    health = record_source_health(
        db,
        blob,
        verify_blob(blob),
        now=now,
    )
    if commit:
        db.commit()
    return health


def _candidate_paths(
    root: Path,
    needed_sizes: set[int],
) -> dict[int, list[Path]]:
    by_size: dict[int, list[Path]] = {}
    if not root.is_dir() or not needed_sizes:
        return by_size
    root_resolved = root.resolve()
    for directory, child_directories, filenames in os.walk(
        root,
        topdown=True,
        onerror=lambda _error: None,
        followlinks=False,
    ):
        child_directories[:] = [
            name for name in child_directories if not name.startswith(".")
        ]
        directory_path = Path(directory)
        for filename in filenames:
            path = directory_path / filename
            try:
                if path.is_symlink():
                    continue
                if (
                    path.suffix.lower() not in SUPPORTED_SUFFIXES
                    or path.suffix.lower() in TEMPORARY_SUFFIXES
                ):
                    continue
                resolved = path.resolve()
                resolved.relative_to(root_resolved)
                size = path.stat().st_size
            except (OSError, ValueError):
                continue
            if size in needed_sizes:
                by_size.setdefault(size, []).append(resolved)
    for paths in by_size.values():
        paths.sort(key=lambda item: (len(item.parts), item.as_posix().casefold()))
    return by_size


def reconcile_sources(
    db: Session,
    root: Path,
    *,
    now: datetime | None = None,
) -> dict:
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    started = time.perf_counter()
    # Hashing the whole NAS must not leave a read transaction open for hours.
    # These are detached snapshots; apply any discovered path changes only
    # after the filesystem work finishes, and only if the path is unchanged.
    with Session(bind=db.get_bind()) as metadata_db:
        blobs = [
            FileBlob(content_hash=row[0], size_bytes=row[1], source_path=row[2])
            for row in metadata_db.execute(select(
                FileBlob.content_hash, FileBlob.size_bytes, FileBlob.source_path,
            )).all()
        ]
    original_paths = {blob.content_hash: blob.source_path for blob in blobs}
    observations: dict[str, dict] = {}
    unhealthy: list[FileBlob] = []
    for blob in blobs:
        observation = verify_blob(blob)
        observations[blob.content_hash] = observation
        if observation["status"] != "verified":
            unhealthy.append(blob)

    candidates = _candidate_paths(
        root.resolve(),
        {blob.size_bytes for blob in unhealthy},
    )
    hash_cache: dict[Path, str | None] = {}
    rebound = 0
    for blob in unhealthy:
        current = Path(blob.source_path)
        for candidate in candidates.get(blob.size_bytes, []):
            if candidate == current:
                continue
            if candidate not in hash_cache:
                try:
                    hash_cache[candidate] = file_sha256(candidate)
                except OSError:
                    hash_cache[candidate] = None
            if hash_cache[candidate] != blob.content_hash:
                continue
            blob.source_path = str(candidate)
            observations[blob.content_hash] = verify_blob(blob)
            rebound += 1
            break

    counts = {
        "total": len(blobs),
        "verified": 0,
        "rebound": rebound,
        "missing": 0,
        "mismatch": 0,
        "failed": 0,
        "skipped_changed": 0,
    }
    current_paths = dict(db.execute(select(FileBlob.content_hash, FileBlob.source_path)).all())
    for blob in blobs:
        original_path = original_paths[blob.content_hash]
        if current_paths.get(blob.content_hash) != original_path:
            counts["skipped_changed"] += 1
            if blob.source_path != original_path:
                counts["rebound"] -= 1
            continue
        if blob.source_path != original_path:
            result = db.execute(update(FileBlob).where(
                FileBlob.content_hash == blob.content_hash,
                FileBlob.source_path == original_path,
            ).values(source_path=blob.source_path))
            if result.rowcount != 1:
                counts["skipped_changed"] += 1
                counts["rebound"] -= 1
                continue
        observation = observations[blob.content_hash]
        record_source_health(
            db,
            blob,
            observation,
            now=checked_at,
        )
        counts[observation["status"]] = (
            counts.get(observation["status"], 0) + 1
        )
    status = (
        "ok"
        if counts["missing"] == 0
        and counts["mismatch"] == 0
        and counts["failed"] == 0
        and counts["skipped_changed"] == 0
        else "warning"
    )
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    db.add(
        AuditLog(
            user_id=None,
            action="source_reconcile",
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
        "duration_ms": duration_ms,
        "checked_at": checked_at.isoformat(),
    }


def source_health_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(SourceHealth.status, func.count(SourceHealth.content_hash))
        .group_by(SourceHealth.status)
    ).all()
    return {status: count for status, count in rows}
