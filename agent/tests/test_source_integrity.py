from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Base, FileBlob, SourceHealth
from app import source_integrity
from app.source_integrity import (
    reconcile_sources,
    source_is_available,
    verify_and_record,
)


def source_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def add_blob(db: Session, source: Path, payload: bytes) -> FileBlob:
    content_hash = hashlib.sha256(payload).hexdigest().upper()
    blob = FileBlob(
        content_hash=content_hash,
        size_bytes=len(payload),
        source_path=str(source),
    )
    db.add(blob)
    db.commit()
    return blob


def test_verify_records_matching_hash(tmp_path) -> None:
    db = source_db()
    source = tmp_path / "source.pdf"
    payload = b"jingao-source"
    source.write_bytes(payload)
    try:
        blob = add_blob(db, source, payload)
        health = verify_and_record(db, blob)
        assert health.status == "verified"
        assert health.observed_hash == blob.content_hash
        assert source_is_available(blob, health) is True
    finally:
        db.close()


def test_reconcile_releases_metadata_connection_while_hashing(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'source.db').as_posix()}")
    Base.metadata.create_all(engine)
    db = Session(engine)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"source-metadata-lock-test")
    add_blob(db, source, source.read_bytes())
    checked_out = set()
    event.listen(engine, "checkout", lambda connection, record, proxy: checked_out.add(id(connection)))
    event.listen(engine, "checkin", lambda connection, record: checked_out.discard(id(connection)))
    original_verify = source_integrity.verify_blob

    def verify_without_connection(blob):
        assert not checked_out, "Hashing must not hold a metadata table lock"
        return original_verify(blob)

    monkeypatch.setattr(source_integrity, "verify_blob", verify_without_connection)
    try:
        result = reconcile_sources(db, tmp_path)
        assert result["counts"]["verified"] == 1
    finally:
        db.close()


def test_same_size_mutation_is_isolated(tmp_path) -> None:
    db = source_db()
    source = tmp_path / "source.pdf"
    original = b"jingao-A"
    source.write_bytes(original)
    try:
        blob = add_blob(db, source, original)
        verify_and_record(db, blob)
        source.write_bytes(b"jingao-B")
        health = verify_and_record(db, blob)
        assert health.status == "mismatch"
        assert health.error_code == "content_hash_mismatch"
        assert source_is_available(blob, health) is False
    finally:
        db.close()


def test_reconcile_rebinds_moved_source_without_logging_path(tmp_path) -> None:
    db = source_db()
    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    old_source = tmp_path / "expired" / "case.pdf"
    payload = b"jingao-moved-source"
    try:
        blob = add_blob(db, old_source, payload)
        moved_source = knowledge_root / "training" / "case.pdf"
        moved_source.parent.mkdir()
        moved_source.write_bytes(payload)

        result = reconcile_sources(db, knowledge_root)
        db.refresh(blob)
        health = db.get(SourceHealth, blob.content_hash)
        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "source_reconcile")
            .order_by(AuditLog.created_at.desc())
        )

        assert result["counts"]["rebound"] == 1
        assert result["counts"]["verified"] == 1
        assert Path(blob.source_path) == moved_source.resolve()
        assert health is not None and health.status == "verified"
        details = json.loads(audit.details_json)
        assert details["counts"]["rebound"] == 1
        assert str(moved_source) not in audit.details_json
        assert moved_source.name not in audit.details_json
    finally:
        db.close()


def test_reconcile_marks_missing_when_no_hash_match(tmp_path) -> None:
    db = source_db()
    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    missing_source = tmp_path / "missing.pdf"
    try:
        blob = add_blob(db, missing_source, b"missing-source")
        result = reconcile_sources(db, knowledge_root)
        health = db.get(SourceHealth, blob.content_hash)
        assert result["status"] == "warning"
        assert result["counts"]["missing"] == 1
        assert health is not None and health.status == "missing"
        assert source_is_available(blob, health) is False
    finally:
        db.close()
