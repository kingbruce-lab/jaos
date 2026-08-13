from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Base,
    Document,
    FileBlob,
    KnowledgeCategory,
    Project,
)
from app.source_integrity import file_sha256
from app.storage_layout import (
    normalize_inbox_storage,
    normalize_web_upload_storage,
)


def test_normalize_web_upload_storage_moves_files_and_updates_database(
    tmp_path,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    knowledge_root = tmp_path / "01_知识资料"
    inbox = knowledge_root / "99_AI入库待审核"
    source = inbox / "cat_test" / "L2" / "Web上传" / "2026-08-10" / "素材.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"image-payload")
    content_hash = file_sha256(source)
    category = KnowledgeCategory(
        key="cat_test",
        name="AI游戏",
        active=True,
    )
    project = Project(
        name="素材",
        domain="cat_test",
        confidentiality="L2",
        knowledge_status="approved",
    )
    blob = FileBlob(
        content_hash=content_hash,
        size_bytes=source.stat().st_size,
        source_path=str(source),
    )
    document = Document(
        project=project,
        file_blob=blob,
        content_hash=content_hash,
        title="素材.png",
        confidentiality="L2",
        knowledge_status="approved",
    )
    db.add_all([category, document])
    db.commit()

    dry_run = normalize_web_upload_storage(
        db,
        knowledge_root,
        inbox,
        apply_changes=False,
    )
    assert dry_run["planned"] == 1
    assert source.is_file()

    applied = normalize_web_upload_storage(
        db,
        knowledge_root,
        inbox,
        apply_changes=True,
    )
    target = knowledge_root / "AI游戏" / "L2" / "素材.png"
    db.refresh(blob)

    assert applied["moved"] == 1
    assert target.read_bytes() == b"image-payload"
    assert not source.exists()
    assert blob.source_path == str(target)
    assert all(
        (knowledge_root / "AI游戏" / level).is_dir()
        for level in ("L1", "L2", "L3", "L4", "L5")
    )
    assert db.scalar(
        select(AuditLog).where(
            AuditLog.action == "normalize_web_upload_storage"
        )
    ) is not None
    db.close()


def test_normalize_inbox_storage_routes_all_files_and_archives_test_data(
    tmp_path,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    knowledge_root = tmp_path / "01_知识资料"
    inbox = knowledge_root / "99_AI入库待审核"
    business_source = inbox / "旧赛事项目" / "总决赛" / "方案.pdf"
    business_copy = inbox / "旧赛事项目" / "总决赛" / "方案副本.pdf"
    synthetic_source = inbox / "synthetic-ingest-a.txt"
    synthetic_copy = inbox / "synthetic-ingest-b.txt"
    metadata = inbox / "旧赛事项目" / ".DS_Store"
    business_source.parent.mkdir(parents=True)
    business_source.write_bytes(b"business")
    business_copy.write_bytes(b"business")
    synthetic_source.write_bytes(b"synthetic")
    synthetic_copy.write_bytes(b"synthetic")
    metadata.write_bytes(b"metadata")

    event_category = KnowledgeCategory(
        key="tournament",
        name="电竞赛事",
        active=True,
    )
    company_category = KnowledgeCategory(
        key="company",
        name="公共资料",
        active=True,
    )
    venue_category = KnowledgeCategory(
        key="venue",
        name="场馆运营",
        active=True,
    )
    business_hash = file_sha256(business_source)
    business_project = Project(
        name="总决赛",
        domain="tournament",
        confidentiality="L2",
        knowledge_status="approved",
    )
    business_blob = FileBlob(
        content_hash=business_hash,
        size_bytes=business_source.stat().st_size,
        source_path=str(business_source),
    )
    business_document = Document(
        project=business_project,
        file_blob=business_blob,
        content_hash=business_hash,
        title="方案.pdf",
        confidentiality="L2",
        knowledge_status="approved",
    )
    synthetic_hash = file_sha256(synthetic_source)
    synthetic_project = Project(
        name="synthetic-ingest-a",
        domain="venue",
        confidentiality="L2",
        knowledge_status="approved",
    )
    synthetic_blob = FileBlob(
        content_hash=synthetic_hash,
        size_bytes=synthetic_source.stat().st_size,
        source_path=str(synthetic_source),
    )
    synthetic_document = Document(
        project=synthetic_project,
        file_blob=synthetic_blob,
        content_hash=synthetic_hash,
        title="synthetic-ingest-a.txt",
        confidentiality="L2",
        knowledge_status="approved",
    )
    db.add_all([
        event_category,
        company_category,
        venue_category,
        business_document,
        synthetic_document,
    ])
    db.commit()

    dry_run = normalize_inbox_storage(
        db,
        knowledge_root,
        inbox,
        apply_changes=False,
    )
    assert dry_run["planned"] == 4
    assert dry_run["metadata_files"] == 1
    assert dry_run["skipped"] == 0

    applied = normalize_inbox_storage(
        db,
        knowledge_root,
        inbox,
        apply_changes=True,
    )
    db.refresh(business_blob)
    db.refresh(synthetic_document)

    assert applied["moved"] == 4
    assert applied["metadata_removed"] == 1
    assert applied["synthetic_archived"] == 2
    assert not list(inbox.rglob("*"))
    assert (
        knowledge_root / "电竞赛事" / "L2" / "总决赛" / "方案.pdf"
    ).is_file()
    assert (
        knowledge_root / "电竞赛事" / "L2" / "总决赛" / "方案副本.pdf"
    ).is_file()
    assert (
        knowledge_root
        / "公共资料"
        / "L1"
        / "系统测试归档"
        / "synthetic-ingest-a.txt"
    ).is_file()
    assert Path(business_blob.source_path) == (
        knowledge_root / "电竞赛事" / "L2" / "总决赛" / "方案.pdf"
    )
    assert synthetic_document.project.domain == "company"
    assert synthetic_document.confidentiality == "L1"
    assert synthetic_document.knowledge_status == "archived"
    db.close()
