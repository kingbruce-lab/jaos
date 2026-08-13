from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main
from app.auth import current_user
from app.database import get_db
from app.main import app
from app.models import AuditLog, Base, KnowledgeCategory, User
from app.taxonomy import seed_default_categories


def category_db() -> tuple[Session, User, User]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    founder = User(
        username="founder",
        display_name="创始人",
        password_hash="x",
        role="founder",
        confidentiality_ceiling="L4",
    )
    employee = User(
        username="employee",
        display_name="员工",
        password_hash="x",
        role="employee",
        confidentiality_ceiling="L2",
        departments_json='["training"]',
    )
    db.add_all([founder, employee])
    db.commit()
    seed_default_categories(db)
    return db, founder, employee


def configure(db: Session, user: User) -> None:
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: user


def test_founder_creates_renames_and_deactivates_custom_category(
    tmp_path,
    monkeypatch,
) -> None:
    db, founder, employee = category_db()
    monkeypatch.setattr(
        main,
        "settings",
        type("Settings", (), {"knowledge_root": tmp_path})(),
    )
    configure(db, founder)
    try:
        client = TestClient(app)
        original = client.post(
            "/v1/admin/categories",
            json={"name": "AI 游戏"},
        )
        category_id = original.json()["id"]
        stable_key = original.json()["key"]
        renamed = client.patch(
            f"/v1/admin/categories/{category_id}",
            json={"name": "AI 游戏业务", "active": False},
        )

        assert original.status_code == 200
        assert stable_key.startswith("cat_")
        assert renamed.status_code == 200
        assert renamed.json()["key"] == stable_key
        assert renamed.json()["name"] == "AI 游戏业务"
        assert renamed.json()["active"] is False
        assert not (tmp_path / "AI 游戏").exists()
        assert all(
            (tmp_path / "AI 游戏业务" / level).is_dir()
            for level in ("L1", "L2", "L3", "L4", "L5")
        )
        assert db.scalar(
            select(AuditLog).where(
                AuditLog.action == "update_knowledge_category"
            )
        ) is not None

        configure(db, employee)
        visible = client.get("/v1/categories")
        assert visible.status_code == 200
        assert stable_key not in {item["key"] for item in visible.json()}
        assert client.post(
            "/v1/admin/categories",
            json={"name": "越权分类"},
        ).status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_account_can_be_assigned_to_new_custom_category(
    tmp_path,
    monkeypatch,
) -> None:
    db, founder, _employee = category_db()
    monkeypatch.setattr(
        main,
        "settings",
        type("Settings", (), {"knowledge_root": tmp_path})(),
    )
    configure(db, founder)
    try:
        client = TestClient(app)
        category = client.post(
            "/v1/admin/categories",
            json={"name": "校园合作"},
        ).json()
        created = client.post(
            "/v1/admin/users",
            json={
                "username": "campus01",
                "display_name": "校园员工",
                "password": "Campus-Password-2026",
                "role": "business",
                "confidentiality_ceiling": "L2",
                "departments": [category["key"]],
            },
        )

        assert created.status_code == 200
        assert created.json()["departments"] == ["*"]
    finally:
        app.dependency_overrides.clear()
        db.close()
