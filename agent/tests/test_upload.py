from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import ingest, main
from app.auth import current_user
from app.database import get_db
from app.main import app
from app.models import AuditLog, Base, Document, KnowledgeCategory, User


def upload_db() -> tuple[Session, User]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    employee = User(
        username="training-upload",
        display_name="培训员工",
        password_hash="x",
        role="employee",
        confidentiality_ceiling="L2",
        departments_json='["training"]',
    )
    db.add_all([
        employee,
        KnowledgeCategory(key="training", name="电竞培训", active=True),
        KnowledgeCategory(key="team", name="电竞战队", active=True),
    ])
    db.commit()
    return db, employee


def configure_upload(monkeypatch, db: Session, user: User, knowledge_root) -> None:
    knowledge_root.mkdir(parents=True)
    inbox = knowledge_root / "99_AI入库待审核"
    inbox.mkdir()
    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(
            knowledge_root=knowledge_root,
            inbox_dir=inbox,
            inbox_max_file_bytes=4 * 1024 * 1024,
        ),
    )
    monkeypatch.setattr(
        ingest,
        "settings",
        SimpleNamespace(
            copy_sources=False,
            managed_source_dir=inbox / "managed",
        ),
    )

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: user


def test_employee_web_upload_enters_own_department_queue(tmp_path, monkeypatch) -> None:
    db, employee = upload_db()
    knowledge_root = tmp_path / "01_知识资料"
    configure_upload(monkeypatch, db, employee, knowledge_root)
    try:
        response = TestClient(app).post(
            "/v1/uploads",
            data={"department": "training", "confidentiality": "L2"},
            files={"file": ("课程复盘.md", "# 课程复盘\n训练成果", "text/markdown")},
        )
        document = db.scalar(select(Document))
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "web_upload"))

        assert response.status_code == 200
        assert response.json()["document_id"] == document.id
        assert document.project.domain == "training"
        assert document.confidentiality == "L2"
        assert document.knowledge_status == "candidate"
        assert document.file_blob.source_path.endswith("课程复盘.md")
        assert audit is not None
        assert (knowledge_root / "电竞培训" / "L2" / "课程复盘.md").is_file()
        assert all(
            (knowledge_root / "电竞培训" / level).is_dir()
            for level in ("L1", "L2", "L3", "L4", "L5")
        )
        assert "Web上传" not in document.file_blob.source_path
        assert str(knowledge_root) not in audit.details_json
        assert "课程复盘.md" not in audit.details_json
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_employee_can_upload_to_any_active_category(tmp_path, monkeypatch) -> None:
    db, employee = upload_db()
    knowledge_root = tmp_path / "01_知识资料"
    configure_upload(monkeypatch, db, employee, knowledge_root)
    try:
        response = TestClient(app).post(
            "/v1/uploads",
            data={"department": "team", "confidentiality": "L2"},
            files={"file": ("越权.md", "不可写入", "text/markdown")},
        )
        assert response.status_code == 200
        assert (knowledge_root / "电竞战队" / "L2" / "越权.md").is_file()
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_video_upload_is_registered_as_previewable_asset(tmp_path, monkeypatch) -> None:
    db, employee = upload_db()
    knowledge_root = tmp_path / "01_知识资料"
    configure_upload(monkeypatch, db, employee, knowledge_root)
    try:
        response = TestClient(app).post(
            "/v1/uploads",
            data={"department": "training", "confidentiality": "L2"},
            files={"file": ("活动现场.mp4", b"synthetic-video-bytes", "video/mp4")},
        )
        document = db.scalar(select(Document))

        assert response.status_code == 200
        assert document.role == "asset"
        assert document.citation_basis == "asset-metadata"
        assert document.knowledge_status == "approved"
        assert response.json()["review_required"] is False
        assert "自动入库" in response.json()["notice"]
        assert main._preview_kind(document) == "video"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_media_folder_upload_preserves_batch_and_nested_folder(tmp_path, monkeypatch) -> None:
    db, employee = upload_db()
    knowledge_root = tmp_path / "01_知识资料"
    configure_upload(monkeypatch, db, employee, knowledge_root)
    try:
        response = TestClient(app).post(
            "/v1/uploads",
            data={
                "department": "training",
                "confidentiality": "L2",
                "folder_name": "2026KPL青训营现场素材",
                "relative_path": "第一天/相机A/DSC03417.JPG",
            },
            files={"file": ("DSC03417.JPG", b"synthetic-image", "image/jpeg")},
        )
        document = db.scalar(select(Document))
        stored = (
            knowledge_root
            / "电竞培训"
            / "L2"
            / "2026KPL青训营现场素材"
            / "第一天"
            / "相机A"
            / "DSC03417.JPG"
        )

        assert response.status_code == 200
        assert response.json()["folder_name"] == "2026KPL青训营现场素材"
        assert stored.is_file()
        assert document.title == "2026KPL青训营现场素材 / DSC03417.JPG"
        assert document.project.name == "2026KPL青训营现场素材"
        assert document.knowledge_status == "approved"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_media_folder_upload_rejects_path_traversal(tmp_path, monkeypatch) -> None:
    db, employee = upload_db()
    knowledge_root = tmp_path / "01_知识资料"
    configure_upload(monkeypatch, db, employee, knowledge_root)
    try:
        response = TestClient(app).post(
            "/v1/uploads",
            data={
                "department": "training",
                "confidentiality": "L2",
                "folder_name": "现场素材",
                "relative_path": "../越界/DSC03417.JPG",
            },
            files={"file": ("DSC03417.JPG", b"synthetic-image", "image/jpeg")},
        )

        assert response.status_code == 422
        assert not list(knowledge_root.rglob("DSC03417.JPG"))
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_archive_upload_is_catalogued_without_extraction(tmp_path, monkeypatch) -> None:
    db, employee = upload_db()
    knowledge_root = tmp_path / "01_知识资料"
    configure_upload(monkeypatch, db, employee, knowledge_root)
    try:
        payload = b"not-a-real-archive-and-must-not-be-opened"
        response = TestClient(app).post(
            "/v1/uploads",
            data={"department": "training", "confidentiality": "L2"},
            files={"file": ("品牌素材.zip", payload, "application/zip")},
        )
        document = db.scalar(select(Document))
        stored = list(knowledge_root.rglob("品牌素材.zip"))

        assert response.status_code == 200
        assert document.role == "asset"
        assert document.citation_basis == "asset-metadata"
        assert document.knowledge_status == "approved"
        assert response.json()["review_required"] is False
        assert len(document.chunks) == 1
        assert document.chunks[0].section == "素材元数据"
        assert document.title in document.chunks[0].text
        assert len(stored) == 1
        assert stored[0].read_bytes() == payload
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_excel_upload_still_requires_human_review(tmp_path, monkeypatch) -> None:
    db, employee = upload_db()
    knowledge_root = tmp_path / "01_知识资料"
    configure_upload(monkeypatch, db, employee, knowledge_root)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["项目", "状态"])
    worksheet.append(["培训项目", "已完成"])
    payload = BytesIO()
    workbook.save(payload)
    try:
        response = TestClient(app).post(
            "/v1/uploads",
            data={"department": "training", "confidentiality": "L2"},
            files={
                "file": (
                    "项目验收.xlsx",
                    payload.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        document = db.scalar(select(Document))

        assert response.status_code == 200
        assert document.knowledge_status == "candidate"
        assert response.json()["review_required"] is True
        assert "审核队列" in response.json()["notice"]
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_existing_library_bytes_are_filtered_without_second_review(
    tmp_path,
    monkeypatch,
) -> None:
    db, employee = upload_db()
    knowledge_root = tmp_path / "01_知识资料"
    configure_upload(monkeypatch, db, employee, knowledge_root)
    payload = "# 公司介绍\n完全相同的现行内容"
    client = TestClient(app)
    try:
        first = client.post(
            "/v1/uploads",
            data={"department": "training", "confidentiality": "L2"},
            files={"file": ("公司介绍.md", payload, "text/markdown")},
        )
        document = db.scalar(select(Document))
        assert document is not None
        document.knowledge_status = "approved"
        db.commit()

        duplicate = client.post(
            "/v1/uploads",
            data={"department": "team", "confidentiality": "L2"},
            files={"file": ("公司介绍副本.md", payload, "text/markdown")},
        )

        assert first.status_code == 200
        assert duplicate.status_code == 200
        assert duplicate.json()["document_id"] == document.id
        assert duplicate.json()["duplicate_filtered"] is True
        assert "完全重复" in duplicate.json()["notice"]
        assert db.scalar(select(func.count(Document.id))) == 1
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_upload_rejects_unsupported_and_oversized_files(tmp_path, monkeypatch) -> None:
    db, employee = upload_db()
    knowledge_root = tmp_path / "01_知识资料"
    configure_upload(monkeypatch, db, employee, knowledge_root)
    try:
        client = TestClient(app)
        unsupported = client.post(
            "/v1/uploads",
            data={"department": "training", "confidentiality": "L2"},
            files={"file": ("恶意程序.exe", b"not-an-executable")},
        )
        oversized = client.post(
            "/v1/uploads",
            data={"department": "training", "confidentiality": "L2"},
            files={"file": ("超限.md", b"x" * (4 * 1024 * 1024 + 1))},
        )

        assert unsupported.status_code == 415
        assert oversized.status_code == 413
        assert not list(knowledge_root.rglob("*.part"))
        assert not list(knowledge_root.rglob("*.exe"))
        assert not list(knowledge_root.rglob("超限.md"))
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_upload_sanitizes_paths_and_never_overwrites_existing_file(tmp_path, monkeypatch) -> None:
    db, employee = upload_db()
    knowledge_root = tmp_path / "01_知识资料"
    configure_upload(monkeypatch, db, employee, knowledge_root)
    try:
        client = TestClient(app)
        first = client.post(
            "/v1/uploads",
            data={"department": "training", "confidentiality": "L2"},
            files={"file": ("../../复盘.md", b"first", "text/markdown")},
        )
        second = client.post(
            "/v1/uploads",
            data={"department": "training", "confidentiality": "L2"},
            files={"file": ("复盘.md", b"second", "text/markdown")},
        )
        stored = sorted(knowledge_root.rglob("复盘*.md"))

        assert first.status_code == 200
        assert second.status_code == 200
        assert len(stored) == 2
        assert {item.read_bytes() for item in stored} == {b"first", b"second"}
        assert not (tmp_path / "复盘.md").exists()
    finally:
        app.dependency_overrides.clear()
        db.close()
