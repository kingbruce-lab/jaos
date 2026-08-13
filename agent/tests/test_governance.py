from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.database import get_db
from app.main import app
from app.models import AuditLog, Base, Chunk, Document, FileBlob, Project, User


def governance_db(tmp_path) -> tuple[Session, dict[str, User], dict[str, Document]]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    users = {
        "founder": User(
            username="founder",
            display_name="创始人",
            password_hash="x",
            role="founder",
            confidentiality_ceiling="L4",
            departments_json='["training"]',
        ),
        "admin": User(
            username="admin",
            display_name="资料管理员",
            password_hash="x",
            role="knowledge_admin",
            confidentiality_ceiling="L4",
            departments_json='["company"]',
        ),
        "employee": User(
            username="employee",
            display_name="员工",
            password_hash="x",
            role="employee",
            confidentiality_ceiling="L3",
            departments_json='["training"]',
        ),
    }
    db.add_all(users.values())
    documents: dict[str, Document] = {}

    def add_document(key: str, title: str, role: str, text: str) -> None:
        source = tmp_path / f"{key}.pdf"
        source.write_bytes(f"%PDF-{key}".encode())
        content_hash = hashlib.sha256(source.read_bytes()).hexdigest().upper()
        project = Project(
            name=f"{key}项目",
            domain="company" if role == "company_profile" else "training",
            confidentiality="L3",
            knowledge_status="approved",
            confirmed=True,
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
            title=title,
            role=role,
            version="v1",
            knowledge_status="approved",
            confidentiality="L3",
            page_count=1,
        )
        db.add(Chunk(document=document, page=1, chunk_index=0, text=text))
        documents[key] = document

    add_document("profile", "京奥电竞公司介绍", "company_profile", "公开公司介绍")
    add_document("ordinary", "电竞课程执行方案", "proposal", "普通课程安排")
    add_document("quote", "电竞培训报价预算", "proposal", "项目报价：10000元")
    add_document("payroll", "教练薪酬绩效考核", "execution", "内部薪酬资料")
    add_document("poster", "赛事公开招募海报", "asset", "公开宣传内容")
    add_document("archive", "项目源文件.zip", "asset", "")
    db.commit()
    return db, users, documents


def override(db: Session, actor: User) -> None:
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: actor


def test_ai_classification_and_manual_governance_are_audited(tmp_path) -> None:
    db, users, documents = governance_db(tmp_path)
    try:
        override(db, users["employee"])
        client = TestClient(app)
        assert client.get("/v1/governance/documents").status_code == 403

        override(db, users["founder"])
        dry_run = client.post(
            "/v1/governance/ai-classify",
            json={
                "dry_run": True,
                "confirmation": "确认AI梳理资料密级",
            },
        )
        assert dry_run.status_code == 200
        assert dry_run.json()["proposed_change_count"] == 3
        assert dry_run.json()["manual_review_count"] == 2

        applied = client.post(
            "/v1/governance/ai-classify",
            json={
                "dry_run": False,
                "confirmation": "确认AI梳理资料密级",
            },
        )
        assert applied.status_code == 200
        assert applied.json()["changed_counts"] == {"L1": 2, "L2": 1, "L3": 0}
        for document in documents.values():
            db.refresh(document)
        assert documents["profile"].confidentiality == "L1"
        assert documents["ordinary"].confidentiality == "L2"
        assert documents["quote"].confidentiality == "L3"
        assert documents["payroll"].confidentiality == "L3"
        assert documents["poster"].confidentiality == "L1"
        assert documents["archive"].confidentiality == "L3"
        assert db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "ai_confidentiality_applied"
            )
        ) == 3

        listing = client.get(
            "/v1/governance/documents?confidentiality=L3&manual_only=true"
        )
        assert listing.status_code == 200
        assert {item["document_id"] for item in listing.json()["items"]} == {
            documents["payroll"].id,
            documents["archive"].id,
        }

        l4_batch = client.post(
            "/v1/governance/documents/confidentiality",
            json={
                "document_ids": [documents["payroll"].id, documents["quote"].id],
                "confidentiality": "L4",
                "reason": "核心敏感资料复核",
                "confirmation": "确认调整资料密级",
            },
        )
        assert l4_batch.status_code == 403

        l4_single = client.post(
            "/v1/governance/documents/confidentiality",
            json={
                "document_ids": [documents["payroll"].id],
                "confidentiality": "L4",
                "reason": "薪酬与绩效资料",
                "confirmation": "确认调整资料密级",
            },
        )
        assert l4_single.status_code == 200
        db.refresh(documents["payroll"])
        assert documents["payroll"].confidentiality == "L4"

        override(db, users["admin"])
        forbidden = client.post(
            "/v1/governance/documents/confidentiality",
            json={
                "document_ids": [documents["quote"].id],
                "confidentiality": "L4",
                "reason": "资料管理员尝试升为核心敏感",
                "confirmation": "确认调整资料密级",
            },
        )
        assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()
