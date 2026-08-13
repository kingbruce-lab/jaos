from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user, hash_password
from app.database import get_db
from app.main import app
from app.models import AuditLog, Base, User
from app.proposal_pptx import render_proposal_pptx
from app.schemas import ProposalBrief


def proposal_db() -> tuple[Session, User]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(
        username="planner",
        display_name="Planner",
        password_hash=hash_password("Planner-Test-Password-2026"),
        role="planner",
        confidentiality_ceiling="L2",
    )
    db.add(user)
    db.commit()
    return db, user


def sample_brief() -> ProposalBrief:
    return ProposalBrief(
        title="高校电竞人才培养项目",
        client="某高校 & 合作方",
        objective="建立可持续的人才培养与实践路径",
        audience="高校学生与指导教师",
        geography="北京",
        duration="6周",
        deliverables="课程、实训成果与结案报告",
    )


def test_proposal_template_exports_editable_eight_slide_pptx() -> None:
    payload = render_proposal_pptx(
        sample_brief(),
        [
            {
                "title": "候选历史方案",
                "page": 8,
                "knowledge_status": "candidate",
            }
        ],
        ["预算"],
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        slides = [
            name
            for name in names
            if name.startswith("ppt/slides/slide")
            and name.endswith(".xml")
        ]
        notes = [
            archive.read(name).decode("utf-8")
            for name in names
            if name.startswith("ppt/notesSlides/notesSlide")
            and name.endswith(".xml")
        ]
        all_xml = b"".join(
            archive.read(name)
            for name in names
            if name.endswith((".xml", ".rels"))
        )

    assert len(slides) == 8
    assert len(notes) == 8
    assert all("[Sources]" in item for item in notes)
    assert b"{{" not in all_xml
    assert "某高校 &amp; 合作方".encode() in all_xml


def test_proposal_pptx_endpoint_returns_download_and_audits() -> None:
    db, planner = proposal_db()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: planner
    try:
        response = TestClient(app).post(
            "/v1/proposals/pptx",
            json=sample_brief().model_dump(),
        )
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "proposal_pptx")
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument"
        )
        assert "attachment" in response.headers["content-disposition"]
        assert zipfile.is_zipfile(io.BytesIO(response.content))
        assert audit is not None
        assert "高校电竞人才培养项目" not in audit.details_json
    finally:
        app.dependency_overrides.clear()
        db.close()
