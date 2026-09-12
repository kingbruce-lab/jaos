from __future__ import annotations

import sqlite3
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pymupdf
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import backup
from app.models import (
    Base,
    Chunk,
    Document,
    DocumentArtifact,
    FileBlob,
    Project,
    ProjectKnowledgeCard,
    SessionToken,
    SourceHealth,
    User,
)


def seeded_backup(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    evaluation_dir = data_dir / "evaluations"
    evaluation_dir.mkdir(parents=True)
    (evaluation_dir / "business_questions.jsonl").write_text(
        '{"id":"backup-case","approved":false}\n',
        encoding="utf-8",
    )
    source_seed = b"Jingao managed source"
    source_hash = hashlib.sha256(source_seed).hexdigest().upper()
    source = data_dir / "sources" / source_hash / "source.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(source_seed)
    reference = data_dir / "derived" / source_hash / "reference.pdf"
    reference.parent.mkdir(parents=True)
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Jingao backup reference")
    pdf.save(reference)
    pdf.close()
    database_path = data_dir / "jingao.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    db = Session(engine)
    project = Project(name="Backup test", confidentiality="L2")
    blob = FileBlob(
        content_hash=source_hash,
        size_bytes=len(source_seed),
        source_path=str(source),
    )
    document = Document(
        project=project,
        file_blob=blob,
        content_hash=source_hash,
        title="source.pdf",
        confidentiality="L2",
        page_count=1,
    )
    db.add(
        Chunk(
            document=document,
            page=1,
            chunk_index=0,
            text="backup restore citation",
        )
    )
    db.add(
        DocumentArtifact(
            document=document,
            kind="reference_pdf",
            path=str(reference),
            content_hash=backup.file_sha256(reference),
            page_count=1,
            status="ready",
        )
    )
    user = User(
        username="backup-founder",
        display_name="Founder",
        password_hash="hash",
        role="founder",
        confidentiality_ceiling="L4",
    )
    db.add(user)
    db.flush()
    db.add(
        ProjectKnowledgeCard(
            project_id=project.id,
            sections_json='{"background":[]}',
            source_fingerprint="F" * 64,
            confidentiality="L2",
            status="confirmed",
            created_by_user_id=user.id,
            confirmed_by_user_id=user.id,
            confirmation_note="backup-test",
            confirmed_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        SessionToken(
            token_hash="H" * 64,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
        )
    )
    db.commit()
    monkeypatch.setattr(
        backup,
        "settings",
        SimpleNamespace(
            database_url=f"sqlite:///{database_path.as_posix()}",
            managed_source_dir=data_dir / "sources",
            data_dir=data_dir,
            evaluation_dir=evaluation_dir,
            policy_version="test-policy",
        ),
    )
    return db, source_hash


def test_backup_verifies_and_restores_to_isolated_directory(
    tmp_path,
    monkeypatch,
) -> None:
    db, source_hash = seeded_backup(tmp_path, monkeypatch)
    result = backup.create_backup(db, tmp_path / "backups")
    verification = backup.verify_backup(Path(result["path"]))
    target = tmp_path / "restored"
    restored = backup.restore_sqlite_backup(
        Path(result["path"]),
        target,
    )

    connection = sqlite3.connect(target / "jingao.db")
    try:
        source_path = connection.execute(
            "SELECT source_path FROM file_blobs WHERE content_hash = ?",
            (source_hash,),
        ).fetchone()[0]
        artifact_path = connection.execute(
            "SELECT path FROM document_artifacts WHERE kind = 'reference_pdf'"
        ).fetchone()[0]
        session_count = connection.execute(
            "SELECT COUNT(*) FROM session_tokens"
        ).fetchone()[0]
        knowledge_card_count = connection.execute(
            "SELECT COUNT(*) FROM project_knowledge_cards"
        ).fetchone()[0]
    finally:
        connection.close()

    assert verification["status"] == "verified"
    assert verification["counts"]["documents"] == 1
    assert verification["counts"]["project_knowledge_cards"] == 1
    assert verification["source_files_verified"] == 1
    assert restored["status"] == "restored"
    assert restored["reference_previews_verified"] == 1
    assert restored["sessions_invalidated"] == 1
    assert Path(source_path).is_file()
    assert Path(artifact_path).is_file()
    assert session_count == 0
    assert knowledge_card_count == 1
    assert (
        target / "evaluations" / "business_questions.jsonl"
    ).is_file()
    assert (
        Path(result["path"])
        / "evaluations"
        / "business_questions.jsonl"
    ).is_file()


def test_backup_copies_verified_original_when_managed_copy_is_absent(
    tmp_path,
    monkeypatch,
) -> None:
    db, source_hash = seeded_backup(tmp_path, monkeypatch)
    managed_source = (
        tmp_path / "data" / "sources" / source_hash / "source.pdf"
    )
    original_source = tmp_path / "knowledge" / "source.pdf"
    original_source.parent.mkdir(parents=True)
    managed_source.replace(original_source)
    blob = db.get(FileBlob, source_hash)
    assert blob is not None
    blob.source_path = str(original_source)
    db.commit()

    result = backup.create_backup(db, tmp_path / "backups")
    verification = backup.verify_backup(Path(result["path"]))

    assert verification["source_files_verified"] == 1
    copied_source = (
        Path(result["path"]) / "sources" / source_hash / "source.pdf"
    )
    assert copied_source.read_bytes() == original_source.read_bytes()


def test_backup_manifest_uses_verified_copy_not_stale_health_timestamp(
    tmp_path,
    monkeypatch,
) -> None:
    db, source_hash = seeded_backup(tmp_path, monkeypatch)
    source = tmp_path / "data" / "sources" / source_hash / "source.pdf"
    db.add(
        SourceHealth(
            content_hash=source_hash,
            status="verified",
            observed_size_bytes=source.stat().st_size,
            observed_mtime_ns=0,
            observed_hash=source_hash,
        )
    )
    db.commit()

    result = backup.create_backup(db, tmp_path / "backups")
    verification = backup.verify_backup(Path(result["path"]))

    assert verification["source_files_verified"] == 1
    assert verification["source_files_missing_at_backup"] == 0


def test_backup_detects_file_tampering(tmp_path, monkeypatch) -> None:
    db, source_hash = seeded_backup(tmp_path, monkeypatch)
    result = backup.create_backup(db, tmp_path / "backups")
    package = Path(result["path"])
    source = next((package / "sources" / source_hash).rglob("*"))
    source.write_bytes(b"tampered")

    with pytest.raises(backup.BackupError, match="backup_size_mismatch"):
        backup.verify_backup(package)


def test_backup_releases_database_connection_before_copying_files(tmp_path, monkeypatch) -> None:
    db, _source_hash = seeded_backup(tmp_path, monkeypatch)
    engine = db.get_bind()
    checked_out = set()
    event.listen(engine, "checkout", lambda connection, record, proxy: checked_out.add(id(connection)))
    event.listen(engine, "checkin", lambda connection, record: checked_out.discard(id(connection)))
    original_copy = backup._copy_tree
    original_sources = backup._copy_content_addressed_sources
    original_manifest = backup._manifest_files

    def copy_without_connection(*args):
        assert not checked_out, "Filesystem copies must not retain database locks"
        return original_copy(*args)

    def sources_without_connection(*args):
        assert not checked_out
        return original_sources(*args)

    def manifest_without_connection(*args):
        assert not checked_out
        return original_manifest(*args)

    monkeypatch.setattr(backup, "_copy_tree", copy_without_connection)
    monkeypatch.setattr(backup, "_copy_content_addressed_sources", sources_without_connection)
    monkeypatch.setattr(backup, "_manifest_files", manifest_without_connection)
    try:
        result = backup.create_backup(db, tmp_path / "backups")
        assert backup.verify_backup(Path(result["path"]))["status"] == "verified"
    finally:
        db.close()
