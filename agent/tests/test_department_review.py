from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.database import get_db
from app.main import app
from app.models import Base, Chunk, Document, FileBlob, KnowledgeCategory, Project, User


def seed_document(db: Session, tmp_path, name: str, domain: str, level: str) -> Document:
    source = tmp_path / f"{name}.txt"
    source.write_text(f"{name} 可预览正文", encoding="utf-8")
    payload = source.read_bytes()
    blob = FileBlob(
        content_hash=hashlib.sha256(payload).hexdigest().upper(),
        size_bytes=len(payload),
        source_path=str(source),
    )
    project = Project(
        name=name,
        domain=domain,
        confidentiality=level,
        knowledge_status="candidate",
        confirmed=False,
    )
    document = Document(
        project=project,
        file_blob=blob,
        content_hash=blob.content_hash,
        title=f"{name}.txt",
        role="proposal",
        version="未确认",
        knowledge_status="candidate",
        confidentiality=level,
        page_count=1,
    )
    db.add(
        Chunk(
            document=document,
            page=1,
            chunk_index=0,
            text=f"{name} 可预览正文",
        )
    )
    db.flush()
    return document


def test_department_owner_reviews_all_categories_with_low_risk_limit(tmp_path) -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    owner = User(
        username="training-owner",
        display_name="培训负责人",
        password_hash="x",
        role="department_owner",
        confidentiality_ceiling="L3",
        departments_json='["training"]',
    )
    training = seed_document(db, tmp_path, "培训低敏", "training", "L2")
    team = seed_document(db, tmp_path, "战队低敏", "team", "L2")
    sensitive = seed_document(db, tmp_path, "培训敏感", "training", "L3")
    db.add_all([
        owner,
        KnowledgeCategory(key="training", name="电竞培训", active=True),
        KnowledgeCategory(key="team", name="电竞战队", active=True),
    ])
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: owner
    try:
        client = TestClient(app)
        queue = client.get("/v1/review/queue")
        queue_ids = {item["document_id"] for item in queue.json()}

        assert queue.status_code == 200
        assert queue_ids == {training.id, team.id}
        assert client.post(f"/v1/review/{team.id}/confirm").status_code == 200
        assert client.post("/v1/review/inbox/scan").status_code == 403
        escaped_proposal = client.post(
            f"/v1/review/{training.id}/proposal",
            json={
                "project_name": "越权改名",
                "client": None,
                "year": 2026,
                "domain": "team",
                "document_role": "proposal",
                "version": "v1.0",
                "confidentiality": "L2",
                "is_final": True,
                "note": None,
            },
        )
        assert escaped_proposal.status_code == 200

        batch = client.post(
            "/v1/review/confirm-batch",
            json={"document_ids": [training.id, sensitive.id]},
        )
        db.refresh(training)
        db.refresh(sensitive)

        assert batch.status_code == 200
        assert batch.json()["confirmed_count"] == 1
        assert batch.json()["failed_count"] == 1
        assert training.knowledge_status == "approved"
        assert sensitive.knowledge_status == "candidate"
    finally:
        app.dependency_overrides.clear()
        db.close()
