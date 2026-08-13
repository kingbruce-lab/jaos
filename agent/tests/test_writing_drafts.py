from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.database import get_db
from app.main import app
from app.models import Base, User
from app.writing_drafts import upsert_latest_writing_draft


def _database() -> tuple[Session, User, User]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    first = User(
        username="writer-one",
        display_name="创作者一",
        password_hash="x",
        role="employee",
        confidentiality_ceiling="L2",
        departments_json="[]",
    )
    second = User(
        username="writer-two",
        display_name="创作者二",
        password_hash="x",
        role="employee",
        confidentiality_ceiling="L2",
        departments_json="[]",
    )
    db.add_all([first, second])
    db.commit()
    return db, first, second


def _configure(db: Session, user: User) -> None:
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: user


def _payload(index: int) -> dict:
    return {
        "title": f"方案 {index}",
        "instruction": f"请编写第 {index} 份电竞培训执行方案",
        "draft": f"# 方案 {index}\n\n这是正文 {index}。[S1]",
        "category": "training",
        "scope": "history",
        "time_scope": "history",
        "generation_mode": "llm",
        "generation_model": "test-model",
        "sources": [{"document_id": f"doc-{index}", "page": index}],
        "response": {"notice": "已生成"},
    }


def test_saved_drafts_are_private_idempotent_and_limited_to_five() -> None:
    db, first, second = _database()
    _configure(db, first)
    try:
        client = TestClient(app)
        saved_ids = []
        for index in range(1, 6):
            response = client.post("/v1/writing/drafts", json=_payload(index))
            assert response.status_code == 200
            assert response.json()["saved_count"] == index
            saved_ids.append(response.json()["draft"]["id"])

        duplicate = client.post("/v1/writing/drafts", json=_payload(1))
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["saved_count"] == 5
        assert duplicate.json()["draft"]["id"] == saved_ids[0]

        overflow = client.post("/v1/writing/drafts", json=_payload(6))
        assert overflow.status_code == 409
        assert "最多保存5条" in overflow.json()["detail"]

        registry = client.get("/v1/writing/drafts").json()
        assert registry["latest"] is None
        assert registry["saved_count"] == 5
        assert registry["max_saved"] == 5
        assert registry["saved"][0]["response"]["draft"]

        _configure(db, second)
        private_registry = client.get("/v1/writing/drafts").json()
        assert private_registry["saved_count"] == 0
        assert client.delete(f"/v1/writing/drafts/{saved_ids[0]}").status_code == 404

        _configure(db, first)
        deleted = client.delete(f"/v1/writing/drafts/{saved_ids[0]}")
        assert deleted.status_code == 200
        assert deleted.json()["saved_count"] == 4
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_latest_slot_can_be_edited_but_not_deleted() -> None:
    db, first, _second = _database()
    latest = upsert_latest_writing_draft(
        db,
        user_id=first.id,
        instruction="请生成一个电竞赛事执行总结",
        content="初始正文",
        category="tournament",
        scope="current",
        generation_mode="llm",
        generation_model="test-model",
        sources=[],
        response={"draft": "初始正文", "sources": []},
    )
    db.commit()
    latest_id = latest.id
    _configure(db, first)
    try:
        client = TestClient(app)
        edited_payload = {
            "title": "编辑后的总结",
            "instruction": "请生成一个电竞赛事执行总结",
            "draft": "人工编辑后的正文",
            "category": "tournament",
            "scope": "current",
            "response": {"draft": "旧正文", "sources": []},
        }
        edited = client.patch("/v1/writing/drafts/latest", json=edited_payload)
        assert edited.status_code == 200
        assert edited.json()["draft"]["id"] == latest_id
        assert edited.json()["draft"]["draft"] == "人工编辑后的正文"
        assert edited.json()["draft"]["response"]["draft"] == "人工编辑后的正文"

        protected = client.delete(f"/v1/writing/drafts/{latest_id}")
        assert protected.status_code == 409
        registry = client.get("/v1/writing/drafts").json()
        assert registry["latest"]["draft"] == "人工编辑后的正文"
        assert registry["saved_count"] == 0
    finally:
        app.dependency_overrides.clear()
        db.close()

