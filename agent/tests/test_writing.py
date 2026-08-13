from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main
from app.auth import current_user
from app.database import get_db
from app.generation import GenerationResult
from app.main import app
from app.models import (
    AuditLog,
    Base,
    Chunk,
    Document,
    FileBlob,
    KnowledgeCategory,
    Project,
    User,
)
from app.writing_drafts import upsert_latest_writing_draft


def add_document(db: Session, tmp_path, category: str, name: str, text: str) -> None:
    source = tmp_path / f"{name}.md"
    source.write_text(text, encoding="utf-8")
    payload = source.read_bytes()
    content_hash = hashlib.sha256(payload).hexdigest().upper()
    blob = FileBlob(
        content_hash=content_hash,
        size_bytes=len(payload),
        source_path=str(source),
    )
    project = Project(
        name=name,
        domain=category,
        confidentiality="L2",
        knowledge_status="approved",
        confirmed=True,
    )
    document = Document(
        project=project,
        file_blob=blob,
        content_hash=content_hash,
        title=f"{name}.md",
        version="v1.0",
        role="closing_report",
        is_final=True,
        knowledge_status="approved",
        confidentiality="L2",
        page_count=1,
    )
    chunk = Chunk(document=document, page=1, chunk_index=0, text=text)
    db.add_all([blob, project, document, chunk])


def writing_db(tmp_path) -> tuple[Session, User, str, str]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    allowed_key = "cat_allowed"
    denied_key = "cat_denied"
    user = User(
        username="writer",
        display_name="策划员工",
        password_hash="x",
        role="planner",
        confidentiality_ceiling="L2",
        departments_json=json.dumps([allowed_key]),
    )
    db.add_all([
        user,
        KnowledgeCategory(key=allowed_key, name="校园合作", active=True),
        KnowledgeCategory(key=denied_key, name="战队商务", active=True),
    ])
    add_document(
        db,
        tmp_path,
        allowed_key,
        "高校实训项目",
        "高校电竞实训项目形成了课程、实训与成果展示的完整路径。",
    )
    add_document(
        db,
        tmp_path,
        denied_key,
        "战队商务项目",
        "战队商务项目包含赞助权益与商业合作方案。",
    )
    db.commit()
    return db, user, allowed_key, denied_key


def configure(db: Session, user: User) -> None:
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: user


def test_writing_uses_only_authorized_category_and_audits_without_prompt(
    tmp_path,
    monkeypatch,
) -> None:
    db, user, allowed_key, denied_key = writing_db(tmp_path)
    configure(db, user)
    instruction = "写一份高校电竞实训方案，说明课程和成果展示"
    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(llm_enabled=True, gateway_api_key="test-key"),
    )

    def generated(_instruction, evidence, *, founder, allow_l3):
        assert founder is False
        assert allow_l3 is False
        return GenerationResult(
            answer="# 高校电竞实训方案\n\n## 项目目标\n形成课程与成果展示路径。[S1]",
            model="grok-test",
            fallback_used=False,
            evidence_document_ids=[evidence[0].document_id],
            outbound_characters=80,
        )

    monkeypatch.setattr(main, "generate_grounded_draft", generated)
    try:
        client = TestClient(app)
        response = client.post(
            "/v1/writing/draft",
            json={
                "instruction": instruction,
                "category": allowed_key,
                "scope": "history",
            },
        )
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "writing_draft")
        )

        assert response.status_code == 200
        assert response.json()["generation_mode"] == "llm"
        assert response.json()["auto_saved"] is True
        assert response.json()["latest_draft_id"]
        assert len(response.json()["sources"]) == 1
        assert response.json()["sources"][0]["domain"] == allowed_key
        assert "[S1]" in response.json()["draft"]
        latest = client.get("/v1/writing/drafts").json()["latest"]
        assert latest["id"] == response.json()["latest_draft_id"]
        assert latest["draft"] == response.json()["draft"]
        assert latest["sources"][0]["excerpt"] == ""
        assert audit is not None
        assert instruction not in audit.details_json
        cross_category = client.post(
            "/v1/writing/draft",
            json={
                "instruction": instruction,
                "category": denied_key,
                "scope": "all",
            },
        )
        assert cross_category.status_code == 200
        assert cross_category.json()["sources"][0]["domain"] == denied_key
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_writing_never_returns_local_excerpt_dump_as_draft(
    tmp_path,
    monkeypatch,
) -> None:
    db, user, allowed_key, _denied_key = writing_db(tmp_path)
    upsert_latest_writing_draft(
        db,
        user_id=user.id,
        instruction="此前成功的创作要求",
        content="此前成功的创作正文",
        category=allowed_key,
        scope="history",
        generation_mode="llm",
        generation_model="test-model",
        sources=[],
        response={"draft": "此前成功的创作正文", "sources": []},
    )
    db.commit()
    configure(db, user)
    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(llm_enabled=False, gateway_api_key=""),
    )
    try:
        response = TestClient(app).post(
            "/v1/writing/draft",
            json={
                "instruction": "写一份高校电竞实训方案",
                "category": allowed_key,
                "scope": "history",
            },
        )

        assert response.status_code == 503
        assert "不会用检索片段冒充初稿" in response.text
        assert "draft" not in response.json()
        registry = TestClient(app).get("/v1/writing/drafts").json()
        assert registry["latest"]["draft"] == "此前成功的创作正文"
        assert db.scalar(
            select(AuditLog).where(
                AuditLog.action == "writing_llm_generation_failed"
            )
        ) is not None
    finally:
        app.dependency_overrides.clear()
        db.close()
