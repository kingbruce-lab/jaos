from __future__ import annotations

import hashlib
import json
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import operations
from app.auth import current_user, hash_password
from app.database import get_db
from app.main import app
from app.models import AuditLog, Base, FileBlob, SourceHealth, User


DiskUsage = namedtuple("DiskUsage", "total used free")


def operation_db() -> tuple[Session, User, User]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    founder = User(
        username="founder",
        display_name="Founder",
        password_hash=hash_password("Founder-Test-Password-2026"),
        role="founder",
        confidentiality_ceiling="L4",
    )
    employee = User(
        username="employee",
        display_name="Employee",
        password_hash=hash_password("Employee-Test-Password-2026"),
        role="employee",
        confidentiality_ceiling="L2",
    )
    db.add_all([founder, employee])
    db.commit()
    return db, founder, employee


def sealed_backup(backup_dir, completed_at: datetime) -> None:
    package = backup_dir / "jingao-test"
    package.mkdir(parents=True)
    manifest = b'{"schema_version":1}\n'
    (package / "manifest.json").write_bytes(manifest)
    (package / "COMPLETE").write_text(
        json.dumps(
            {
                "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                "completed_at": completed_at.isoformat(),
            }
        ),
        encoding="utf-8",
    )


def configure_settings(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        operations,
        "settings",
        SimpleNamespace(
            data_dir=tmp_path,
            knowledge_root=tmp_path,
            backup_dir=tmp_path / "backups",
            offsite_backup_status_file=(
                tmp_path / "backups" / ".jaos-offsite-status.json"
            ),
            evaluation_dir=tmp_path / "evaluations",
            backup_max_age_seconds=93600,
            offsite_backup_max_age_seconds=604800,
            disk_warning_percent=80,
            disk_critical_percent=90,
            memory_warning_percent=80,
            memory_critical_percent=90,
            gateway_api_key=None,
            llm_enabled=False,
            llm_l3_enabled=False,
            primary_model="grok-4.5",
            fallback_model="deepseek-test",
            embedding_enabled=False,
            embedding_model="test-embedding",
            embedding_l3_enabled=False,
            inbox_scan_interval_seconds=900,
            source_health_max_age_seconds=93600,
        ),
    )


def verified_offsite_status(backup_dir, completed_at: datetime) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / ".jaos-offsite-status.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "code": "verified",
                "message": "第二物理介质备份已复制并完成全量哈希校验",
                "media_configured": True,
                "media_available": True,
                "separate_device": True,
                "verified": True,
                "latest_package": "jingao-test",
                "latest_completed_at": completed_at.isoformat(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

def successful_scan(db: Session, at: datetime) -> None:
    db.add(
        AuditLog(
            action="inbox_scan",
            details_json=json.dumps(
                {
                    "status": "ok",
                    "counts": {
                        "discovered": 0,
                        "ingested": 0,
                        "unchanged": 0,
                        "deferred": 0,
                        "unsupported": 0,
                        "failed": 0,
                        "skipped": 0,
                    },
                }
            ),
            created_at=at,
        )
    )
    db.commit()


def test_operations_reports_sealed_recent_backup(tmp_path, monkeypatch) -> None:
    db, _founder, _employee = operation_db()
    now = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
    configure_settings(monkeypatch, tmp_path)
    sealed_backup(tmp_path / "backups", now - timedelta(hours=1))
    verified_offsite_status(tmp_path / "backups", now - timedelta(hours=2))
    successful_scan(db, now - timedelta(minutes=5))
    try:
        payload = operations.collect_operations_status(
            db,
            now=now,
            disk_usage=lambda _path: DiskUsage(1000, 400, 600),
            memory_usage=lambda: (300, 1000),
        )
        assert payload["status"] == "ok"
        assert payload["components"]["database"]["status"] == "ok"
        assert payload["components"]["backup"]["manifest_sealed"] is True
        assert payload["components"]["backup"]["age_seconds"] == 3600
        assert payload["components"]["offsite_backup"]["verified"] is True
        assert payload["components"]["offsite_backup"]["separate_device"] is True
    finally:
        db.close()


def test_operations_warns_on_disk_and_stale_backup(tmp_path, monkeypatch) -> None:
    db, _founder, _employee = operation_db()
    now = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
    configure_settings(monkeypatch, tmp_path)
    sealed_backup(tmp_path / "backups", now - timedelta(days=2))
    try:
        payload = operations.collect_operations_status(
            db,
            now=now,
            disk_usage=lambda _path: DiskUsage(1000, 850, 150),
            memory_usage=lambda: (300, 1000),
        )
        assert payload["status"] == "warning"
        assert payload["components"]["storage"]["status"] == "warning"
        assert payload["components"]["backup"]["status"] == "warning"
        assert any("数据盘" in item for item in payload["recommendations"])
        assert any("主备份" in item for item in payload["recommendations"])
    finally:
        db.close()


def test_operations_endpoint_is_admin_only(tmp_path, monkeypatch) -> None:
    db, founder, employee = operation_db()
    configure_settings(monkeypatch, tmp_path)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: employee
    try:
        client = TestClient(app)
        assert client.get("/v1/operations/status").status_code == 403
        app.dependency_overrides[current_user] = lambda: founder
        response = client.get("/v1/operations/status")
        assert response.status_code == 200
        assert set(response.json()["components"]) == {
            "database",
            "storage",
            "memory",
            "backup",
            "offsite_backup",
            "gateway",
            "evaluation",
            "ingestion",
            "source_integrity",
        }
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_operations_never_treats_single_disk_as_second_backup(
    tmp_path,
    monkeypatch,
) -> None:
    db, _founder, _employee = operation_db()
    now = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
    configure_settings(monkeypatch, tmp_path)
    sealed_backup(tmp_path / "backups", now - timedelta(hours=1))
    successful_scan(db, now - timedelta(minutes=5))
    try:
        payload = operations.collect_operations_status(
            db,
            now=now,
            disk_usage=lambda _path: DiskUsage(1000, 400, 600),
            memory_usage=lambda: (300, 1000),
        )
        offsite = payload["components"]["offsite_backup"]
        assert payload["status"] == "warning"
        assert offsite["status"] == "warning"
        assert offsite["verified"] is False
        assert "第二物理介质" in offsite["message"]
        assert any("同一块NAS硬盘不算" in item for item in payload["recommendations"])
    finally:
        db.close()


def test_operations_warns_when_verified_offsite_backup_is_stale(
    tmp_path,
    monkeypatch,
) -> None:
    db, _founder, _employee = operation_db()
    now = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
    configure_settings(monkeypatch, tmp_path)
    sealed_backup(tmp_path / "backups", now - timedelta(hours=1))
    verified_offsite_status(tmp_path / "backups", now - timedelta(days=8))
    successful_scan(db, now - timedelta(minutes=5))
    try:
        payload = operations.collect_operations_status(
            db,
            now=now,
            disk_usage=lambda _path: DiskUsage(1000, 400, 600),
            memory_usage=lambda: (300, 1000),
        )
        offsite = payload["components"]["offsite_backup"]
        assert offsite["status"] == "warning"
        assert offsite["age_seconds"] == 8 * 86400
        assert "超过允许时限" in offsite["message"]
    finally:
        db.close()


def test_manual_source_reconciliation_is_admin_only(
    tmp_path,
    monkeypatch,
) -> None:
    db, founder, employee = operation_db()
    configure_settings(monkeypatch, tmp_path)
    source = tmp_path / "source.pdf"
    payload = b"source-integrity"
    source.write_bytes(payload)
    blob = FileBlob(
        content_hash=hashlib.sha256(payload).hexdigest().upper(),
        size_bytes=len(payload),
        source_path=str(source),
    )
    db.add(blob)
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: employee
    try:
        client = TestClient(app)
        assert (
            client.post("/v1/operations/reconcile-sources").status_code
            == 403
        )
        app.dependency_overrides[current_user] = lambda: founder
        response = client.post("/v1/operations/reconcile-sources")
        health = db.get(SourceHealth, blob.content_hash)
        assert response.status_code == 200
        assert response.json()["counts"]["verified"] == 1
        assert health is not None and health.status == "verified"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_public_health_is_sanitized_and_monitor_flags_warning(
    tmp_path,
    monkeypatch,
) -> None:
    db, _founder, _employee = operation_db()
    configure_settings(monkeypatch, tmp_path)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        ready = client.get("/readyz")
        monitor = client.get("/monitorz")

        assert ready.status_code == 200
        assert monitor.status_code == 503
        assert ready.json()["status"] == "warning"
        assert ready.json()["components"]["backup"] == {"status": "warning"}
        serialized = json.dumps(ready.json())
        assert str(tmp_path) not in serialized
        assert "embedding_model" not in serialized
        assert "free_gb" not in serialized
    finally:
        app.dependency_overrides.clear()
        db.close()
