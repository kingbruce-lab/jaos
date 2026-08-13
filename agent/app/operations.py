from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .config import settings
from .evaluation import evaluation_component
from .models import AuditLog, FileBlob, InboxIssue, SourceHealth


def _level(percent: float, warning: int, critical: int) -> str:
    if percent >= critical:
        return "critical"
    if percent >= warning:
        return "warning"
    return "ok"


def _gib(value: int) -> float:
    return round(value / (1024**3), 2)


def _memory_usage() -> tuple[int, int] | None:
    current = Path("/sys/fs/cgroup/memory.current")
    maximum = Path("/sys/fs/cgroup/memory.max")
    if current.is_file() and maximum.is_file():
        try:
            used = int(current.read_text(encoding="ascii").strip())
            raw_maximum = maximum.read_text(encoding="ascii").strip()
            if raw_maximum != "max":
                total = int(raw_maximum)
                if total > 0:
                    # memory.current includes reclaimable filesystem cache.
                    # Docker's own memory reporting subtracts inactive_file;
                    # using the raw value made large OCR/model files produce
                    # false critical alarms even with ample host memory.
                    stat_path = Path("/sys/fs/cgroup/memory.stat")
                    if stat_path.is_file():
                        stats = {
                            key: int(value)
                            for key, value in (
                                line.split(maxsplit=1)
                                for line in stat_path.read_text(
                                    encoding="ascii"
                                ).splitlines()
                                if " " in line
                            )
                        }
                        used = max(0, used - stats.get("inactive_file", 0))
                    return used, total
        except (OSError, ValueError):
            pass

    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        state = MemoryStatus()
        state.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            used = state.total_physical - state.available_physical
            return used, state.total_physical

    if hasattr(os, "sysconf"):
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            total_pages = os.sysconf("SC_PHYS_PAGES")
            available_pages = os.sysconf("SC_AVPHYS_PAGES")
            total = page_size * total_pages
            used = total - (page_size * available_pages)
            if total > 0:
                return used, total
        except (OSError, ValueError):
            pass
    return None


def _backup_status(
    backup_dir: Path,
    now: datetime,
    max_age_seconds: int,
) -> dict:
    if not backup_dir.is_dir():
        return {
            "status": "warning",
            "message": "尚未发现备份目录",
            "latest_completed_at": None,
            "age_seconds": None,
            "manifest_sealed": False,
        }
    candidates = [
        path
        for path in backup_dir.iterdir()
        if path.is_dir()
        and (path / "COMPLETE").is_file()
        and (path / "manifest.json").is_file()
    ]
    if not candidates:
        return {
            "status": "warning",
            "message": "尚未发现完整备份",
            "latest_completed_at": None,
            "age_seconds": None,
            "manifest_sealed": False,
        }
    latest = max(candidates, key=lambda item: (item / "COMPLETE").stat().st_mtime)
    try:
        complete = json.loads((latest / "COMPLETE").read_text(encoding="utf-8"))
        manifest_bytes = (latest / "manifest.json").read_bytes()
        manifest_sealed = (
            hashlib.sha256(manifest_bytes).hexdigest().lower()
            == str(complete["manifest_sha256"]).lower()
        )
        completed_at = datetime.fromisoformat(complete["completed_at"])
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        age_seconds = max(0, int((now - completed_at).total_seconds()))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "status": "critical",
            "message": "最近备份的完成标记无法验证",
            "latest_completed_at": None,
            "age_seconds": None,
            "manifest_sealed": False,
        }
    if not manifest_sealed:
        state = "critical"
        message = "最近备份清单与完成标记不一致"
    elif age_seconds > max_age_seconds:
        state = "warning"
        message = "最近完整备份已超过允许时限"
    else:
        state = "ok"
        message = "最近备份已完成并封存"
    return {
        "status": state,
        "message": message,
        "latest_completed_at": completed_at.astimezone(timezone.utc).isoformat(),
        "age_seconds": age_seconds,
        "manifest_sealed": manifest_sealed,
    }


def _offsite_backup_status(
    status_file: Path,
    now: datetime,
    max_age_seconds: int,
) -> dict:
    """Report a verified copy on a physically separate backup device.

    The NAS host-side synchronizer is authoritative because a container
    cannot prove whether two bind mounts are backed by different disks.
    Missing status is intentionally a warning rather than a fabricated
    success: the current single-disk deployment is not a second backup.
    """

    base = {
        "latest_completed_at": None,
        "age_seconds": None,
        "media_configured": False,
        "media_available": False,
        "separate_device": False,
        "verified": False,
        "latest_package": None,
    }
    if not status_file.is_file():
        return {
            **base,
            "status": "warning",
            "code": "status_missing",
            "message": "尚未配置第二物理介质；主备份仍只在NAS单盘",
        }
    try:
        payload = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError):
        return {
            **base,
            "status": "critical",
            "code": "status_invalid",
            "message": "第二备份状态文件损坏，无法确认异机备份",
        }
    completed_at = None
    age_seconds = None
    if payload.get("verified") and payload.get("latest_completed_at"):
        try:
            completed_at = datetime.fromisoformat(
                str(payload["latest_completed_at"]).replace("Z", "+00:00")
            )
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            age_seconds = max(0, int((now - completed_at).total_seconds()))
        except ValueError:
            completed_at = None
    state = str(payload.get("status") or "warning")
    if state not in {"ok", "warning", "critical"}:
        state = "critical"
    verified = bool(payload.get("verified"))
    separate_device = bool(payload.get("separate_device"))
    if state == "ok" and not (verified and separate_device and completed_at):
        state = "critical"
        message = "第二备份状态不完整，不能视为有效异机备份"
    elif state == "ok" and age_seconds is not None and age_seconds > max_age_seconds:
        state = "warning"
        message = "第二物理介质备份已超过允许时限"
    else:
        message = str(payload.get("message") or "第二备份需要检查")
    return {
        "status": state,
        "code": str(payload.get("code") or "unknown"),
        "message": message,
        "latest_completed_at": (
            completed_at.astimezone(timezone.utc).isoformat()
            if completed_at else None
        ),
        "age_seconds": age_seconds,
        "media_configured": bool(payload.get("media_configured")),
        "media_available": bool(payload.get("media_available")),
        "separate_device": separate_device,
        "verified": verified,
        "latest_package": payload.get("latest_package") or None,
    }


def _ingestion_status(db: Session, now: datetime) -> dict:
    latest = db.scalar(
        select(AuditLog)
        .where(AuditLog.action == "inbox_scan")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    open_issues = db.scalar(
        select(func.count(InboxIssue.id)).where(
            InboxIssue.resolved_at.is_(None)
        )
    ) or 0
    if latest is None:
        return {
            "status": "warning",
            "message": "待审核目录尚未完成首次扫描",
            "latest_scan_at": None,
            "age_seconds": None,
            "open_issue_count": open_issues,
            "counts": {},
        }
    created_at = latest.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_seconds = max(0, int((now - created_at).total_seconds()))
    try:
        details = json.loads(latest.details_json)
        counts = details.get("counts", {})
        scan_status = details.get("status", "warning")
    except (TypeError, json.JSONDecodeError):
        counts = {}
        scan_status = "warning"
    stale_after = max(
        3600,
        settings.inbox_scan_interval_seconds * 3,
    )
    if scan_status == "unavailable":
        state = "warning"
        message = "待审核目录不可用或尚未挂载"
    elif age_seconds > stale_after:
        state = "warning"
        message = "待审核目录扫描已超过计划周期"
    elif counts.get("failed", 0) or counts.get("unsupported", 0):
        state = "warning"
        message = "待审核目录存在需要处理的文件"
    else:
        state = "ok"
        message = "待审核目录扫描正常"
    return {
        "status": state,
        "message": message,
        "latest_scan_at": created_at.astimezone(timezone.utc).isoformat(),
        "age_seconds": age_seconds,
        "open_issue_count": open_issues,
        "counts": counts,
    }


def _source_integrity_status(db: Session, now: datetime) -> dict:
    latest = db.scalar(
        select(AuditLog)
        .where(AuditLog.action == "source_reconcile")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    total = db.scalar(select(func.count(FileBlob.content_hash))) or 0
    rows = db.execute(
        select(SourceHealth.status, func.count(SourceHealth.content_hash))
        .group_by(SourceHealth.status)
    ).all()
    counts = {status: count for status, count in rows}
    observed = sum(counts.values())
    counts["unverified"] = max(
        counts.get("unverified", 0),
        total - observed,
    )
    if counts.get("mismatch", 0) or counts.get("failed", 0):
        state = "critical"
        message = "存在内容变化或核验失败的原件"
    elif counts.get("missing", 0):
        state = "warning"
        message = "存在失联原件，已从正常检索隔离"
    elif counts.get("unverified", 0):
        state = "warning"
        message = "部分原件尚未完成首次哈希核验"
    else:
        state = "ok"
        message = "已登记原件的哈希与路径正常"
    latest_at = None
    age_seconds = None
    if latest is not None:
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        latest_at = created_at.astimezone(timezone.utc).isoformat()
        age_seconds = max(0, int((now - created_at).total_seconds()))
        if (
            age_seconds > settings.source_health_max_age_seconds
            and state == "ok"
        ):
            state = "warning"
            message = "原件完整性核验已超过计划周期"
    elif total:
        state = "warning"
        message = "尚未完成首次原件完整性核验"
    return {
        "status": state,
        "message": message,
        "latest_completed_at": latest_at,
        "age_seconds": age_seconds,
        "counts": counts,
        "unhealthy_count": (
            counts.get("missing", 0)
            + counts.get("mismatch", 0)
            + counts.get("failed", 0)
        ),
    }


def collect_operations_status(
    db: Session,
    *,
    now: datetime | None = None,
    disk_usage: Callable[[Path], shutil._ntuple_diskusage] = shutil.disk_usage,
    memory_usage: Callable[[], tuple[int, int] | None] = _memory_usage,
) -> dict:
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)

    try:
        db.execute(text("SELECT 1"))
        database = {"status": "ok", "message": "数据库连接正常"}
    except Exception:
        database = {"status": "critical", "message": "数据库连接失败"}

    try:
        disk = disk_usage(settings.data_dir)
        disk_percent = round((disk.used / disk.total) * 100, 1) if disk.total else 100.0
        disk_state = _level(
            disk_percent,
            settings.disk_warning_percent,
            settings.disk_critical_percent,
        )
        storage = {
            "status": disk_state,
            "message": (
                "存储空间正常"
                if disk_state == "ok"
                else "存储空间接近上限"
                if disk_state == "warning"
                else "存储空间不足"
            ),
            "used_percent": disk_percent,
            "free_gb": _gib(disk.free),
            "total_gb": _gib(disk.total),
        }
    except OSError:
        storage = {
            "status": "critical",
            "message": "无法读取数据盘状态",
            "used_percent": None,
            "free_gb": None,
            "total_gb": None,
        }

    memory_values = memory_usage()
    if memory_values and memory_values[1] > 0:
        used_memory, total_memory = memory_values
        memory_percent = round((used_memory / total_memory) * 100, 1)
        memory_state = _level(
            memory_percent,
            settings.memory_warning_percent,
            settings.memory_critical_percent,
        )
        memory = {
            "status": memory_state,
            "message": (
                "内存使用正常"
                if memory_state == "ok"
                else "内存使用偏高"
                if memory_state == "warning"
                else "内存使用已达警戒线"
            ),
            "used_percent": memory_percent,
            "used_gb": _gib(used_memory),
            "total_gb": _gib(total_memory),
        }
    else:
        memory = {
            "status": "warning",
            "message": "当前环境无法读取内存状态",
            "used_percent": None,
            "used_gb": None,
            "total_gb": None,
        }

    backup = _backup_status(
        settings.backup_dir,
        checked_at,
        settings.backup_max_age_seconds,
    )
    offsite_backup = _offsite_backup_status(
        settings.offsite_backup_status_file,
        checked_at,
        settings.offsite_backup_max_age_seconds,
    )
    gateway = {
        "status": (
            "configured"
            if settings.gateway_api_key
            else "disabled"
        ),
        "message": (
            "网关密钥已注入，生成与语义检索按独立开关执行"
            if settings.gateway_api_key
            else "未注入网关密钥，保持本地确定性检索"
        ),
        "llm_enabled": settings.llm_enabled,
        "primary_model": settings.primary_model,
        "fallback_model": settings.fallback_model,
        "embedding_enabled": settings.embedding_enabled,
        "embedding_model": settings.embedding_model,
        "l3_outbound_enabled": bool(
            settings.embedding_l3_enabled or settings.llm_l3_enabled
        ),
    }
    evaluation = evaluation_component(settings.evaluation_dir)
    ingestion = _ingestion_status(db, checked_at)
    source_integrity = _source_integrity_status(db, checked_at)

    components = {
        "database": database,
        "storage": storage,
        "memory": memory,
        "backup": backup,
        "offsite_backup": offsite_backup,
        "gateway": gateway,
        "evaluation": evaluation,
        "ingestion": ingestion,
        "source_integrity": source_integrity,
    }
    actionable_states = [
        item["status"]
        for name, item in components.items()
        if name not in {"gateway", "evaluation"}
    ]
    overall = (
        "critical"
        if "critical" in actionable_states
        else "warning"
        if "warning" in actionable_states
        else "ok"
    )
    recommendations: list[str] = []
    if database["status"] == "critical":
        recommendations.append("检查数据库容器与连接配置。")
    if storage["status"] in {"warning", "critical"}:
        recommendations.append("检查数据盘占用，达到 80% 前转移备份或扩容。")
    if memory["status"] in {"warning", "critical"}:
        recommendations.append("暂停解析批处理并检查容器内存占用。")
    if backup["status"] in {"warning", "critical"}:
        recommendations.append("立即执行一次NAS主备份并完成哈希校验。")
    if offsite_backup["status"] in {"warning", "critical"}:
        recommendations.append(
            "插入并配置第二块物理介质，执行 manage.sh offsite-backup；同一块NAS硬盘不算第二备份。"
        )
    if ingestion["status"] in {"warning", "critical"}:
        recommendations.append("检查待审核目录挂载、扫描周期和未解决文件。")
    if source_integrity["status"] in {"warning", "critical"}:
        recommendations.append(
            "运行原件完整性核验；移动文件会按哈希重连，缺失或变化文件需恢复原件。"
        )
    if not recommendations:
        recommendations.append("当前运行指标正常，继续按日备份、按季度恢复演练。")
    return {
        "status": overall,
        "components": components,
        "recommendations": recommendations,
        "thresholds": {
            "disk_warning_percent": settings.disk_warning_percent,
            "disk_critical_percent": settings.disk_critical_percent,
            "memory_warning_percent": settings.memory_warning_percent,
            "memory_critical_percent": settings.memory_critical_percent,
            "backup_max_age_seconds": settings.backup_max_age_seconds,
            "offsite_backup_max_age_seconds": (
                settings.offsite_backup_max_age_seconds
            ),
        },
        "generated_at": checked_at.isoformat(),
    }
