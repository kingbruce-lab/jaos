from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main
from app.auth import current_user, hash_password
from app.database import get_db
from app.main import app
from app.models import (
    AuditLog,
    Base,
    Chunk,
    Document,
    DocumentArtifact,
    FileBlob,
    InboxIssue,
    KnowledgeCategory,
    Project,
    ReviewProposal,
    User,
)


def review_db(tmp_path) -> tuple[Session, dict[str, User], Document]:
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
            password_hash=hash_password("Founder-Test-Password-2026"),
            role="founder",
            confidentiality_ceiling="L4",
        ),
        "admin": User(
            username="knowledge-admin",
            display_name="资料管理员",
            password_hash=hash_password("Knowledge-Test-Password-2026"),
            role="knowledge_admin",
            confidentiality_ceiling="L3",
        ),
        "low_admin": User(
            username="low-admin",
            display_name="低密级资料管理员",
            password_hash=hash_password("Low-Admin-Test-Password-2026"),
            role="knowledge_admin",
            confidentiality_ceiling="L2",
        ),
        "employee": User(
            username="employee",
            display_name="员工",
            password_hash=hash_password("Employee-Test-Password-2026"),
            role="employee",
            confidentiality_ceiling="L2",
        ),
    }
    source = tmp_path / "synthetic-review.pdf"
    source.write_bytes(b"%PDF-1.4\nsynthetic")
    source_payload = source.read_bytes()
    project = Project(
        name="待确认项目",
        client=None,
        year=2026,
        domain="training",
        confidentiality="L3",
        knowledge_status="candidate",
        confirmed=False,
    )
    blob = FileBlob(
        content_hash=hashlib.sha256(source_payload).hexdigest().upper(),
        size_bytes=len(source_payload),
        source_path=str(source),
    )
    document = Document(
        project=project,
        file_blob=blob,
        content_hash=blob.content_hash,
        title="合成测试资料",
        role="proposal",
        version="未确认",
        is_final=False,
        knowledge_status="candidate",
        confidentiality="L3",
        page_count=1,
    )
    chunk = Chunk(
        document=document,
        page=1,
        chunk_index=0,
        text="仅用于自动化测试的可引用内容。",
    )
    ocr_check = DocumentArtifact(
        document=document,
        kind="ocr_text",
        status="ready",
        page_count=1,
    )
    db.add_all([
        *users.values(),
        project,
        blob,
        document,
        chunk,
        ocr_check,
        KnowledgeCategory(key="training", name="电竞培训", active=True),
    ])
    db.commit()
    return db, users, document


def configure_overrides(db: Session, actor: User) -> None:
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: actor


def proposal_payload() -> dict:
    return {
        "project_name": "合成项目已核对",
        "client": "合成客户",
        "year": 2026,
        "domain": "training",
        "document_role": "closing_report",
        "version": "v1.0",
        "confidentiality": "L2",
        "is_final": True,
        "note": "仅用于自动化测试",
    }


def test_admin_proposal_does_not_change_document_truth(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    configure_overrides(db, users["admin"])
    try:
        response = TestClient(app).post(
            f"/v1/review/{document.id}/proposal",
            json=proposal_payload(),
        )
        db.refresh(document)
        db.refresh(document.project)
        proposal = db.scalar(select(ReviewProposal))
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "review_proposed")
        )

        assert response.status_code == 200
        assert response.json()["document_unchanged"] is True
        assert response.json()["knowledge_status"] == "candidate"
        assert proposal is not None
        assert proposal.status == "pending_founder"
        assert document.role == "proposal"
        assert document.version == "未确认"
        assert document.is_final is False
        assert document.confidentiality == "L3"
        assert document.project.name == "待确认项目"
        assert document.project.confirmed is False
        assert audit is not None
        assert "合成项目已核对" not in audit.details_json
        assert json.loads(audit.details_json)["field_names"]
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_admin_can_preview_and_confirm_with_one_click(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    configure_overrides(db, users["admin"])
    try:
        client = TestClient(app)
        proposed = client.post(
            f"/v1/review/{document.id}/proposal",
            json=proposal_payload(),
        )
        assert proposed.status_code == 200

        queue = client.get("/v1/review/queue")
        item = queue.json()[0]
        assert item["preview_available"] is True
        assert item["confirm_eligible"] is True

        confirmed = client.post(f"/v1/review/{document.id}/confirm")
        db.refresh(document)
        db.refresh(document.project)
        proposal = db.scalar(select(ReviewProposal))
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "review_confirmed")
        )

        assert confirmed.status_code == 200
        assert confirmed.json()["knowledge_status"] == "approved"
        assert document.knowledge_status == "approved"
        assert document.project.knowledge_status == "approved"
        assert document.project.confirmed is True
        assert document.project.name == "合成项目已核对"
        assert document.role == "closing_report"
        assert document.version == "v1.0"
        assert proposal is not None and proposal.status == "applied"
        assert audit is not None
        assert client.get("/v1/review/queue").json() == []
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_one_click_confirmation_requires_available_preview(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    source = document.file_blob.source_path
    Path(source).unlink()
    configure_overrides(db, users["founder"])
    try:
        response = TestClient(app).post(
            f"/v1/review/{document.id}/confirm"
        )
        db.refresh(document)
        assert response.status_code == 409
        assert "原件失联" in response.text
        assert document.knowledge_status == "candidate"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_founder_can_batch_confirm_l3_documents(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    configure_overrides(db, users["founder"])
    try:
        response = TestClient(app).post(
            "/v1/review/confirm-batch",
            json={"document_ids": [document.id]},
        )
        db.refresh(document)

        assert response.status_code == 200
        assert response.json()["confirmed_count"] == 1
        assert response.json()["newly_confirmed_count"] == 1
        assert response.json()["already_confirmed_count"] == 0
        assert response.json()["failed_count"] == 0
        assert document.knowledge_status == "approved"

        retried = TestClient(app).post(
            "/v1/review/confirm-batch",
            json={"document_ids": [document.id] * 177},
        )

        assert retried.status_code == 200
        assert retried.json()["confirmed_count"] == 1
        assert retried.json()["newly_confirmed_count"] == 0
        assert retried.json()["already_confirmed_count"] == 1
        assert retried.json()["failed_count"] == 0
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_batch_confirmation_keeps_l4_as_individual_review(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    document.confidentiality = "L4"
    document.project.confidentiality = "L4"
    db.commit()
    configure_overrides(db, users["founder"])
    try:
        response = TestClient(app).post(
            "/v1/review/confirm-batch",
            json={"document_ids": [document.id]},
        )
        db.refresh(document)

        assert response.status_code == 200
        assert response.json()["confirmed_count"] == 0
        assert response.json()["failed_count"] == 1
        assert "L4" in response.json()["failed"][0]["detail"]
        assert document.knowledge_status == "candidate"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_reject_ingestion_retains_source_and_removes_candidate_from_queue(
    tmp_path,
) -> None:
    db, users, document = review_db(tmp_path)
    source_path = Path(document.file_blob.source_path)
    configure_overrides(db, users["founder"])
    try:
        client = TestClient(app)
        response = client.post(
            f"/v1/review/{document.id}/decline",
            json={
                "confirmation": "确认拒绝入库",
                "reason": "内容不属于公司资料",
            },
        )
        db.refresh(document)
        db.refresh(document.project)
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "ingestion_rejected")
        )

        assert response.status_code == 200
        assert response.json()["source_retained"] is True
        assert document.knowledge_status == "rejected"
        assert document.project.knowledge_status == "rejected"
        assert source_path.is_file()
        assert client.get("/v1/review/queue").json() == []
        assert audit is not None
        assert json.loads(audit.details_json)["reason"] == "内容不属于公司资料"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_batch_reject_is_idempotent_and_l4_remains_individual(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    configure_overrides(db, users["founder"])
    try:
        client = TestClient(app)
        first = client.post(
            "/v1/review/reject-batch",
            json={
                "document_ids": [document.id],
                "confirmation": "确认拒绝入库",
            },
        )
        second = client.post(
            "/v1/review/reject-batch",
            json={
                "document_ids": [document.id],
                "confirmation": "确认拒绝入库",
            },
        )

        assert first.status_code == 200
        assert first.json()["newly_rejected_count"] == 1
        assert second.status_code == 200
        assert second.json()["already_rejected_count"] == 1

        document.knowledge_status = "candidate"
        document.confidentiality = "L4"
        document.project.knowledge_status = "candidate"
        document.project.confidentiality = "L4"
        db.commit()
        l4 = client.post(
            "/v1/review/reject-batch",
            json={
                "document_ids": [document.id],
                "confirmation": "确认拒绝入库",
            },
        )
        db.refresh(document)

        assert l4.status_code == 200
        assert l4.json()["failed_count"] == 1
        assert "L4" in l4.json()["failed"][0]["detail"]
        assert document.knowledge_status == "candidate"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_only_founder_can_apply_and_candidate_status_is_preserved(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    configure_overrides(db, users["admin"])
    try:
        client = TestClient(app)
        proposed = client.post(
            f"/v1/review/{document.id}/proposal",
            json=proposal_payload(),
        ).json()["proposal"]

        forbidden = client.post(
            f"/v1/review/{document.id}/apply",
            json={
                "proposal_id": proposed["id"],
                "confirmation": "确认应用",
            },
        )
        configure_overrides(db, users["founder"])
        invalid_phrase = client.post(
            f"/v1/review/{document.id}/apply",
            json={
                "proposal_id": proposed["id"],
                "confirmation": "应用",
            },
        )
        applied = client.post(
            f"/v1/review/{document.id}/apply",
            json={
                "proposal_id": proposed["id"],
                "confirmation": "确认应用",
            },
        )
        db.refresh(document)
        db.refresh(document.project)
        review = db.get(ReviewProposal, proposed["id"])
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "review_applied")
        )

        assert forbidden.status_code == 403
        assert invalid_phrase.status_code == 422
        assert applied.status_code == 200
        assert applied.json()["current_promotion"] is False
        assert document.project.name == "合成项目已核对"
        assert document.project.client == "合成客户"
        assert document.project.confirmed is True
        assert document.role == "closing_report"
        assert document.version == "v1.0"
        assert document.is_final is True
        assert document.knowledge_status == "candidate"
        assert document.project.knowledge_status == "candidate"
        # Project confidentiality never becomes weaker as a side effect.
        assert document.project.confidentiality == "L3"
        assert review is not None and review.status == "applied"
        assert audit is not None
        assert json.loads(audit.details_json)["current_promotion"] is False
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_founder_can_reject_without_mutating_document(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    configure_overrides(db, users["admin"])
    try:
        client = TestClient(app)
        proposal = client.post(
            f"/v1/review/{document.id}/proposal",
            json=proposal_payload(),
        ).json()["proposal"]
        configure_overrides(db, users["founder"])
        rejected = client.post(
            f"/v1/review/{document.id}/reject",
            json={
                "proposal_id": proposal["id"],
                "confirmation": "确认退回",
                "reason": "项目名称需重新核对",
            },
        )
        db.refresh(document)
        review = db.get(ReviewProposal, proposal["id"])

        assert rejected.status_code == 200
        assert rejected.json()["document_unchanged"] is True
        assert document.role == "proposal"
        assert document.version == "未确认"
        assert document.knowledge_status == "candidate"
        assert review is not None
        assert review.status == "rejected"
        assert review.decision_note == "项目名称需重新核对"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_publish_current_supersedes_exact_lineage_with_founder_confirmation(
    tmp_path,
) -> None:
    db, users, document = review_db(tmp_path)
    client = TestClient(app)
    configure_overrides(db, users["admin"])
    try:
        proposed = client.post(
            f"/v1/review/{document.id}/proposal",
            json=proposal_payload(),
        ).json()["proposal"]
        configure_overrides(db, users["founder"])
        applied = client.post(
            f"/v1/review/{document.id}/apply",
            json={
                "proposal_id": proposed["id"],
                "confirmation": "确认应用",
            },
        )
        assert applied.status_code == 200

        old_source = tmp_path / "synthetic-old-current.pdf"
        old_source.write_bytes(b"%PDF-1.4\nold-current")
        old_payload = old_source.read_bytes()
        old_project = Project(
            name=document.project.name,
            client=document.project.client,
            year=2025,
            domain=document.project.domain,
            confidentiality="L2",
            knowledge_status="current",
            confirmed=True,
        )
        old_blob = FileBlob(
            content_hash=hashlib.sha256(old_payload).hexdigest().upper(),
            size_bytes=len(old_payload),
            source_path=str(old_source),
        )
        old_document = Document(
            project=old_project,
            file_blob=old_blob,
            content_hash=old_blob.content_hash,
            title="旧版结案报告",
            role=document.role,
            version="v0.9",
            is_final=True,
            knowledge_status="current",
            confidentiality="L2",
            page_count=1,
            valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        old_chunk = Chunk(
            document=old_document,
            page=1,
            chunk_index=0,
            text="旧版历史内容。",
        )
        db.add_all([old_project, old_blob, old_document, old_chunk])
        db.commit()

        queue = client.get("/v1/review/queue")
        assert queue.status_code == 200
        item = next(
            row for row in queue.json()
            if row["document_id"] == document.id
        )
        assert item["metadata_confirmed"] is True
        assert item["publication_eligible"] is True
        assert item["publication_blockers"] == []
        assert [
            row["document_id"] for row in item["replacement_candidates"]
        ] == [old_document.id]

        configure_overrides(db, users["admin"])
        forbidden = client.post(
            f"/v1/review/{document.id}/publish",
            json={
                "confirmation": "确认发布为当前版本",
                "supersedes_document_ids": [old_document.id],
            },
        )
        configure_overrides(db, users["founder"])
        invalid_phrase = client.post(
            f"/v1/review/{document.id}/publish",
            json={
                "confirmation": "发布",
                "supersedes_document_ids": [old_document.id],
            },
        )
        stale_scope = client.post(
            f"/v1/review/{document.id}/publish",
            json={
                "confirmation": "确认发布为当前版本",
                "supersedes_document_ids": [],
            },
        )
        published = client.post(
            f"/v1/review/{document.id}/publish",
            json={
                "confirmation": "确认发布为当前版本",
                "supersedes_document_ids": [old_document.id],
                "note": "自动化测试发布",
            },
        )

        db.refresh(document)
        db.refresh(document.project)
        db.refresh(old_document)
        db.refresh(old_project)
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "knowledge_published"
            )
        )
        assert forbidden.status_code == 403
        assert invalid_phrase.status_code == 422
        assert stale_scope.status_code == 409
        assert published.status_code == 200
        assert published.json()["knowledge_status"] == "current"
        assert document.knowledge_status == "current"
        assert document.valid_from is not None
        assert document.valid_to is None
        assert document.supersedes_document_id == old_document.id
        assert document.project.knowledge_status == "current"
        assert old_document.knowledge_status == "superseded"
        assert old_document.valid_to is not None
        assert old_project.knowledge_status == "superseded"
        assert audit is not None
        assert "确认发布为当前版本" not in audit.details_json
        assert json.loads(audit.details_json)[
            "superseded_document_ids"
        ] == [old_document.id]
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_publish_is_blocked_until_metadata_and_final_state_are_confirmed(
    tmp_path,
) -> None:
    db, users, document = review_db(tmp_path)
    configure_overrides(db, users["founder"])
    try:
        response = TestClient(app).post(
            f"/v1/review/{document.id}/publish",
            json={
                "confirmation": "确认发布为当前版本",
                "supersedes_document_ids": [],
            },
        )
        db.refresh(document)
        assert response.status_code == 409
        assert "元数据尚未由创始人确认" in response.text
        assert "尚未标记为定稿" in response.text
        assert document.knowledge_status == "candidate"
        assert document.valid_from is None
        assert db.scalar(
            select(AuditLog).where(
                AuditLog.action == "knowledge_published"
            )
        ) is None
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_review_queue_filters_by_role_and_confidentiality(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    try:
        client = TestClient(app)
        configure_overrides(db, users["employee"])
        assert client.get("/v1/review/queue").status_code == 403

        configure_overrides(db, users["low_admin"])
        assert client.get("/v1/review/queue").json() == []
        assert client.post(
            f"/v1/review/{document.id}/proposal",
            json=proposal_payload(),
        ).status_code == 404

        configure_overrides(db, users["founder"])
        queue = client.get("/v1/review/queue")
        assert queue.status_code == 200
        assert len(queue.json()) == 1
        assert queue.json()[0]["review_state"] == "待预览确认"
        assert queue.json()[0]["knowledge_status"] == "candidate"
        assert queue.json()[0]["uploader_name"] == "NAS用户未识别"
        assert queue.json()[0]["uploader_username"] is None
        assert queue.json()[0]["upload_source"] == "nas"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_review_queue_shows_original_web_uploader(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    db.add(
        AuditLog(
            user_id=users["employee"].id,
            action="web_upload",
            document_ids_json=json.dumps([document.id]),
        )
    )
    db.commit()
    configure_overrides(db, users["founder"])
    try:
        response = TestClient(app).get("/v1/review/queue")

        assert response.status_code == 200
        assert response.json()[0]["uploader_name"] == "员工"
        assert response.json()[0]["uploader_username"] == "employee"
        assert response.json()[0]["upload_source"] == "web"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_review_queue_shows_nas_filesystem_owner(tmp_path) -> None:
    db, users, document = review_db(tmp_path)
    document.file_blob.source_owner_name = "jalijicheng"
    document.file_blob.source_owner_uid = 1010
    db.commit()
    configure_overrides(db, users["founder"])
    try:
        response = TestClient(app).get("/v1/review/queue")

        assert response.status_code == 200
        assert response.json()[0]["uploader_name"] == "jalijicheng"
        assert response.json()[0]["uploader_username"] == "jalijicheng"
        assert response.json()[0]["upload_source"] == "nas"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_only_founder_can_read_unclassified_inbox_issue_names(tmp_path) -> None:
    db, users, _document = review_db(tmp_path)
    db.add(
        InboxIssue(
            relative_path="未分类/敏感候选.pdf",
            status="failed",
            error_code="PdfReadError",
            message="解析失败：PdfReadError",
            size_bytes=10,
            modified_ns=1,
        )
    )
    db.commit()
    try:
        client = TestClient(app)
        configure_overrides(db, users["admin"])
        assert client.get("/v1/review/inbox/issues").status_code == 403

        configure_overrides(db, users["founder"])
        response = client.get("/v1/review/inbox/issues")
        assert response.status_code == 200
        assert response.json()[0]["relative_path"] == "未分类/敏感候选.pdf"
        assert "source_path" not in response.json()[0]

        issue_id = response.json()[0]["id"]
        ignored = client.post(f"/v1/review/inbox/issues/{issue_id}/ignore")
        assert ignored.status_code == 200
        assert ignored.json()["status"] == "ignored"
        assert client.get("/v1/review/inbox/issues").json() == []
        db.refresh(db.get(InboxIssue, issue_id))
        assert db.get(InboxIssue, issue_id).status == "ignored"
        assert db.get(InboxIssue, issue_id).resolved_at is not None
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_manual_scan_returns_counts_without_file_names(
    tmp_path,
    monkeypatch,
) -> None:
    db, users, _document = review_db(tmp_path)
    configure_overrides(db, users["admin"])
    monkeypatch.setattr(
        main,
        "scan_inbox",
        lambda _db, _root=None: {
            "status": "warning",
            "counts": {
                "discovered": 2,
                "ingested": 1,
                "unchanged": 0,
                "deferred": 0,
                "unsupported": 1,
                "failed": 0,
                "skipped": 0,
            },
            "items": [
                {"relative_path": "不应返回.pdf", "status": "ingested"},
            ],
            "duration_ms": 12.3,
            "checked_at": "2026-07-27T00:00:00+00:00",
        },
    )
    try:
        response = TestClient(app).post("/v1/review/inbox/scan")
        payload = response.json()
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "manual_inbox_scan")
        )

        assert response.status_code == 200
        assert payload["counts"]["ingested"] == 1
        assert "items" not in payload
        assert "不应返回.pdf" not in response.text
        assert audit is not None
        assert "不应返回.pdf" not in audit.details_json
    finally:
        app.dependency_overrides.clear()
        db.close()
