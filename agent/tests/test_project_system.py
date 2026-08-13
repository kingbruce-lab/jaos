from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import project_system
from app.auth import current_user
from app.database import get_db
from app.main import app
from app.models import (
    AuditLog,
    Base,
    ManagedProject,
    ProjectDeletionRequest,
    ProjectReview,
    User,
)


def _database() -> tuple[Session, dict[str, User]]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    users = {
        "business": User(
            username="pm-business", display_name="项目经理",
            password_hash="x", role="employee",
            organization_role="business", confidentiality_ceiling="L3",
        ),
        "second_business": User(
            username="pm-business-2", display_name="其他项目经理",
            password_hash="x", role="employee",
            organization_role="business", confidentiality_ceiling="L3",
        ),
        "administrative": User(
            username="admin-staff", display_name="行政员工",
            password_hash="x", role="employee",
            organization_role="administrative", confidentiality_ceiling="L4",
        ),
        "finance": User(
            username="jalihemin", display_name="李贺敏",
            password_hash="x", role="employee",
            organization_role="finance", confidentiality_ceiling="L4",
        ),
        "other_finance": User(
            username="other-finance", display_name="其他财务",
            password_hash="x", role="employee",
            organization_role="finance", confidentiality_ceiling="L4",
        ),
        "founder": User(
            username="founder", display_name="叶靖波",
            password_hash="x", role="founder",
            organization_role="management", confidentiality_ceiling="L5",
        ),
        "anli": User(
            username="jaanliyuan", display_name="安利园",
            password_hash="x", role="founder",
            organization_role="management", confidentiality_ceiling="L5",
        ),
        "manager": User(
            username="other-manager", display_name="其他管理",
            password_hash="x", role="founder",
            organization_role="management", confidentiality_ceiling="L5",
        ),
    }
    db = Session(engine, expire_on_commit=False)
    db.add_all(users.values())
    db.commit()
    return db, users


def _configure(monkeypatch, tmp_path, db: Session, user: User) -> TestClient:
    monkeypatch.setattr(
        project_system,
        "settings",
        SimpleNamespace(
            knowledge_root=tmp_path / "knowledge",
            inbox_max_file_bytes=10 * 1024 * 1024,
        ),
    )

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


def _review(client: TestClient, project_id: str, stage: str, decision: str = "approved"):
    return client.post(
        f"/v1/pm/projects/{project_id}/review",
        json={"stage": stage, "decision": decision, "note": "同意"},
    )


def test_project_founder_approval_and_closing(tmp_path, monkeypatch) -> None:
    db, users = _database()
    client = _configure(monkeypatch, tmp_path, db, users["business"])
    try:
        created = client.post(
            "/v1/pm/projects",
            data={
                "project_no": "JADJ-Cc26A1",
                "name": "KPL青训营",
                "company_name": "京奥电竞（北京）科技有限公司",
                "client": "测试客户",
                "business_category": "电竞培训",
                "planned_start": "2026-08-01",
                "planned_end": "2026-10-31",
                "objective": "完成青训营策划、执行和结案。",
                "members_json": '[" 项目经理 ", "执行负责人", "项目经理"]',
                "contract_amount": "500000",
                "budget_revenue": "500000",
                "budget_cost": "300000",
            },
            files={"proposal_file": ("立项方案.pptx", b"pptx-test", "application/octet-stream")},
        )
        assert created.status_code == 200
        project_id = created.json()["id"]
        assert created.json()["project_no"] == "JADJ-Cc26A1"
        assert created.json()["status"] == "draft"
        assert created.json()["members"] == ["执行负责人"]
        assert db.get(ManagedProject, project_id).members_json == '["执行负责人"]'

        cashflow_ids: dict[str, str] = {}
        for direction, due_date, amount in (
            ("receivable", "2026-08-15", "200000"),
            ("payable", "2026-08-10", "100000"),
        ):
            cashflow_response = client.post(
                f"/v1/pm/projects/{project_id}/cashflow",
                json={"direction": direction, "due_date": due_date, "amount": amount},
            )
            assert cashflow_response.status_code == 200
            cashflow_ids[direction] = cashflow_response.json()["id"]
        submitted = client.post(f"/v1/pm/projects/{project_id}/submit-initiation")
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "initiation_review"

        app.dependency_overrides[current_user] = lambda: users["manager"]
        assert _review(client, project_id, "initiation").status_code == 403
        app.dependency_overrides[current_user] = lambda: users["other_finance"]
        assert _review(client, project_id, "initiation").status_code == 403

        app.dependency_overrides[current_user] = lambda: users["finance"]
        assert _review(client, project_id, "initiation").status_code == 403
        app.dependency_overrides[current_user] = lambda: users["anli"]
        assert _review(client, project_id, "initiation").status_code == 403
        # A legacy finance approval in the same review round must not prevent
        # the new founder-only policy from advancing the project.
        db.add(ProjectReview(
            project_id=project_id,
            stage="initiation",
            review_round=1,
            reviewer_slot="finance",
            reviewer_user_id=users["finance"].id,
            decision="approved",
            note="旧流程遗留复核",
        ))
        db.commit()
        app.dependency_overrides[current_user] = lambda: users["founder"]
        response = _review(client, project_id, "initiation")
        assert response.status_code == 200
        assert response.json()["status"] == "active"
        assert len(db.scalars(select(ProjectReview)).all()) == 2

        app.dependency_overrides[current_user] = lambda: users["business"]
        progress = client.post(
            f"/v1/pm/projects/{project_id}/progress",
            json={
                "progress_percent": 60,
                "current_stage": "执行中",
                "completed": "完成招募与第一阶段课程",
                "next_step": "完成赛事和结案材料",
                "risks": "回款时间待确认",
                "needs_coordination": True,
            },
        )
        assert progress.status_code == 200
        closing = client.post(
            f"/v1/pm/projects/{project_id}/submit-closing",
            data={
                "closing_summary": "项目按计划完成，客户已验收。",
                "actual_revenue": "500000",
                "actual_cost": "280000",
                "actual_receivable": "100000",
                "actual_payable": "20000",
            },
            files={"closing_file": ("结案报告.pdf", b"pdf-test", "application/pdf")},
        )
        assert closing.status_code == 200
        assert closing.json()["status"] == "closing_review"

        app.dependency_overrides[current_user] = lambda: users["founder"]
        response = _review(client, project_id, "closing")
        assert response.status_code == 200
        assert response.json()["status"] == "closed"
        assert response.json()["progress_percent"] == 100
        project = db.get(ManagedProject, project_id)
        assert project.status == "closed"
        assert response.json()["portfolio_group"] == "closed_unpaid"
        assert response.json()["outstanding_receivable"] == "200000.00"

        app.dependency_overrides[current_user] = lambda: users["finance"]
        blocked_archive = client.post(
            f"/v1/pm/projects/{project_id}/archive",
            json={"action": "archive"},
        )
        assert blocked_archive.status_code == 409
        received = client.patch(
            f"/v1/pm/cashflow/{cashflow_ids['receivable']}/actual",
            json={"actual_amount": 200000, "actual_date": "2026-11-10"},
        )
        assert received.status_code == 200
        archived = client.post(
            f"/v1/pm/projects/{project_id}/archive",
            json={"action": "archive"},
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "archived"
        assert archived.json()["portfolio_group"] == "archived"

        app.dependency_overrides[current_user] = lambda: users["founder"]
        restored = client.post(
            f"/v1/pm/projects/{project_id}/archive",
            json={"action": "restore"},
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "closed"
        assert restored.json()["portfolio_group"] == "ready_archive"
        assert list((tmp_path / "knowledge" / "项目管理").rglob("结案报告.pdf")) == []
        assert list((tmp_path / "knowledge" / "项目管理").rglob("*结案报告.pdf"))
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_pm_updates_process_finance_only_while_project_is_running(
    tmp_path, monkeypatch
) -> None:
    db, users = _database()
    client = _configure(monkeypatch, tmp_path, db, users["business"])
    try:
        created = client.post(
            "/v1/pm/projects",
            data={
                "project_no": "FEISHU-FIN-01",
                "name": "项目过程资金测试",
                "company_name": "京奥电竞（北京）科技有限公司",
                "client": "测试甲方",
                "client_contact": "测试联系人",
                "business_category": "电竞培训",
                "members_json": '["执行同事"]',
                "planned_start": "2026-08-01",
                "planned_end": "2026-10-31",
                "objective": "验证项目经理过程资金填报与权限。",
            },
        )
        assert created.status_code == 200
        project_id = created.json()["id"]
        assert Decimal(str(created.json()["process_received"])) == Decimal("0")
        assert Decimal(str(created.json()["process_spent"])) == Decimal("0")
        assert Decimal(str(created.json()["process_advanced"])) == Decimal("0")

        before_start = client.patch(
            f"/v1/pm/projects/{project_id}/process-finance",
            json={
                "process_received": 100000,
                "process_spent": 50000,
                "process_advanced": 20000,
            },
        )
        assert before_start.status_code == 409

        assert client.post(
            f"/v1/pm/projects/{project_id}/submit-initiation"
        ).status_code == 200
        app.dependency_overrides[current_user] = lambda: users["founder"]
        assert _review(client, project_id, "initiation").status_code == 200

        app.dependency_overrides[current_user] = lambda: users["business"]
        updated = client.patch(
            f"/v1/pm/projects/{project_id}/process-finance",
            json={
                "process_received": 180000,
                "process_spent": 120000,
                "process_advanced": 45000,
            },
        )
        assert updated.status_code == 200
        assert Decimal(str(updated.json()["process_received"])) == Decimal("180000")
        assert Decimal(str(updated.json()["process_spent"])) == Decimal("120000")
        assert Decimal(str(updated.json()["process_advanced"])) == Decimal("45000")
        assert updated.json()["process_finance_updated_at"] is not None
        assert db.get(ManagedProject, project_id).process_advanced == Decimal("45000")
        assert db.scalar(
            select(AuditLog).where(AuditLog.action == "pm_process_finance_update")
        ) is not None

        invalid = client.patch(
            f"/v1/pm/projects/{project_id}/process-finance",
            json={
                "process_received": -1,
                "process_spent": 0,
                "process_advanced": 0,
            },
        )
        assert invalid.status_code == 422

        app.dependency_overrides[current_user] = lambda: users["finance"]
        forbidden = client.patch(
            f"/v1/pm/projects/{project_id}/process-finance",
            json={
                "process_received": 1,
                "process_spent": 1,
                "process_advanced": 1,
            },
        )
        assert forbidden.status_code == 403

        app.dependency_overrides[current_user] = lambda: users["second_business"]
        assert client.patch(
            f"/v1/pm/projects/{project_id}/process-finance",
            json={
                "process_received": 1,
                "process_spent": 1,
                "process_advanced": 1,
            },
        ).status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_project_rejection_returns_to_business(tmp_path, monkeypatch) -> None:
    db, users = _database()
    client = _configure(monkeypatch, tmp_path, db, users["business"])
    try:
        created = client.post(
            "/v1/pm/projects",
            data={
                "project_no": "JADJ-Cc26A2",
                "name": "测试项目",
                "company_name": "京奥电竞",
                "client": "测试客户",
                "business_category": "赛事",
                "planned_start": "2026-08-01",
                "planned_end": "2026-09-01",
                "objective": "测试驳回后重新提交。",
                "members_json": '["执行成员"]',
            },
        )
        project_id = created.json()["id"]
        client.post(f"/v1/pm/projects/{project_id}/submit-initiation")
        app.dependency_overrides[current_user] = lambda: users["founder"]
        rejected = _review(client, project_id, "initiation", "rejected")
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "initiation_rejected"
        app.dependency_overrides[current_user] = lambda: users["business"]
        resubmitted = client.post(f"/v1/pm/projects/{project_id}/submit-initiation")
        assert resubmitted.status_code == 200
        assert resubmitted.json()["status"] == "initiation_review"
        assert db.get(ManagedProject, project_id).initiation_round == 2
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_project_owner_can_edit_and_founder_controls_deletion(tmp_path, monkeypatch) -> None:
    db, users = _database()
    client = _configure(monkeypatch, tmp_path, db, users["business"])
    try:
        created = client.post(
            "/v1/pm/projects",
            data={
                "project_no": "JADJ-Cc26A3",
                "name": "待修改项目",
                "company_name": "京奥电竞",
                "client": "测试客户",
                "business_category": "赛事",
                "planned_start": "2026-08-01",
                "planned_end": "2026-09-01",
                "objective": "验证项目经理编辑和删除申请。",
                "members_json": '["执行成员"]',
            },
        )
        assert created.status_code == 200
        project_id = created.json()["id"]

        updated = client.patch(
            f"/v1/pm/projects/{project_id}",
            json={
                "name": "已修改项目",
                "company_name": "京奥电竞（北京）科技有限公司",
                "client": "新客户",
                "business_category": "电竞赛事",
                "planned_start": "2026-08-02",
                "planned_end": "2026-09-02",
                "objective": "项目经理已完成基础信息修改。",
                "members": [" 项目经理 ", "执行负责人", "项目经理"],
                "contract_amount": 100000,
                "budget_revenue": 100000,
                "budget_cost": 60000,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "已修改项目"
        assert updated.json()["members"] == ["执行负责人"]

        app.dependency_overrides[current_user] = lambda: users["manager"]
        assert client.patch(
            f"/v1/pm/projects/{project_id}",
            json={
                "name": "越权修改",
                "company_name": "京奥电竞（北京）科技有限公司",
                "client": "新客户",
                "business_category": "电竞赛事",
                "planned_start": "2026-08-02",
                "planned_end": "2026-09-02",
                "objective": "该修改不应获得授权。",
                "members": ["越权人员"],
                "contract_amount": 0,
                "budget_revenue": 0,
                "budget_cost": 0,
            },
        ).status_code == 409

        app.dependency_overrides[current_user] = lambda: users["business"]
        requested = client.post(
            f"/v1/pm/projects/{project_id}/deletion-request",
            json={"reason": "测试项目不再需要"},
        )
        assert requested.status_code == 200
        request_id = requested.json()["request_id"]
        assert db.get(ProjectDeletionRequest, request_id).status == "pending"

        app.dependency_overrides[current_user] = lambda: users["anli"]
        assert client.post(
            f"/v1/pm/deletion-requests/{request_id}/decide",
            json={"decision": "approved", "note": "尝试越权审批"},
        ).status_code == 403

        app.dependency_overrides[current_user] = lambda: users["founder"]
        rejected = client.post(
            f"/v1/pm/deletion-requests/{request_id}/decide",
            json={"decision": "rejected", "note": "先保留"},
        )
        assert rejected.status_code == 200
        assert db.get(ManagedProject, project_id).status == "draft"

        app.dependency_overrides[current_user] = lambda: users["business"]
        requested_again = client.post(
            f"/v1/pm/projects/{project_id}/deletion-request",
            json={"reason": "确认属于测试数据"},
        )
        second_request_id = requested_again.json()["request_id"]

        app.dependency_overrides[current_user] = lambda: users["founder"]
        approved = client.post(
            f"/v1/pm/deletion-requests/{second_request_id}/decide",
            json={"decision": "approved", "note": "批准删除"},
        )
        assert approved.status_code == 200
        assert approved.json()["project_deleted"] is True
        assert db.get(ManagedProject, project_id).status == "deleted"
        assert client.get(f"/v1/pm/projects/{project_id}").status_code == 404
        assert all(item["id"] != project_id for item in client.get("/v1/pm/projects").json()["items"])
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_project_visibility_is_limited_to_management_finance_and_own_business(tmp_path, monkeypatch) -> None:
    db, users = _database()
    client = _configure(monkeypatch, tmp_path, db, users["business"])
    try:
        first = client.post(
            "/v1/pm/projects",
            data={
                "project_no": "JADJ-Cc26A4",
                "name": "第一项目经理项目",
                "company_name": "京奥电竞",
                "client": "客户一",
                "business_category": "赛事",
                "planned_start": "2026-08-01",
                "planned_end": "2026-09-01",
                "objective": "仅第一项目经理可见。",
                "members_json": '["第一执行成员"]',
            },
        )
        assert first.status_code == 200

        app.dependency_overrides[current_user] = lambda: users["second_business"]
        second = client.post(
            "/v1/pm/projects",
            data={
                "project_no": "JADJ-Cc26A5",
                "name": "第二项目经理项目",
                "company_name": "京奥电竞",
                "client": "客户二",
                "business_category": "培训",
                "planned_start": "2026-08-02",
                "planned_end": "2026-10-01",
                "objective": "仅第二项目经理可见。",
                "members_json": '["第二执行成员"]',
            },
        )
        assert second.status_code == 200
        own_items = client.get("/v1/pm/projects").json()["items"]
        assert [item["name"] for item in own_items] == ["第二项目经理项目"]

        app.dependency_overrides[current_user] = lambda: users["finance"]
        assert len(client.get("/v1/pm/projects").json()["items"]) == 2
        app.dependency_overrides[current_user] = lambda: users["founder"]
        assert len(client.get("/v1/pm/projects").json()["items"]) == 2

        app.dependency_overrides[current_user] = lambda: users["administrative"]
        assert client.get("/v1/pm/projects").status_code == 403
        assert client.get(f"/v1/pm/projects/{first.json()['id']}").status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_execution_team_is_required_on_write_and_legacy_empty_project_is_readable(
    tmp_path, monkeypatch
) -> None:
    assert project_system._normalize_project_members(
        ["ＰＭ", "pm", " 执行成员 "], required=True, manager_name="PM"
    ) == ["执行成员"]
    db, users = _database()
    client = _configure(monkeypatch, tmp_path, db, users["business"])
    base_form = {
        "project_no": "JADJ-Cc26A6",
        "name": "执行团队测试项目",
        "company_name": "京奥电竞（北京）科技有限公司",
        "client": "测试客户",
        "business_category": "电竞培训",
        "planned_start": "2026-08-01",
        "planned_end": "2026-09-01",
        "objective": "验证执行团队名单的创建、修改、权限和旧数据兼容。",
    }
    try:
        missing = client.post("/v1/pm/projects", data=base_form)
        assert missing.status_code == 422
        assert missing.json()["detail"] == "请至少填写1名执行团队成员"

        whitespace = client.post(
            "/v1/pm/projects",
            data={**base_form, "members_json": '["  "]'},
        )
        assert whitespace.status_code == 422

        only_manager = client.post(
            "/v1/pm/projects",
            data={**base_form, "members_json": '[" 项目经理 "]'},
        )
        assert only_manager.status_code == 422
        assert only_manager.json()["detail"] == "请至少填写1名执行团队成员"

        created = client.post(
            "/v1/pm/projects",
            data={**base_form, "members_json": '[" 陈岩 ", "李明", "陈岩"]'},
        )
        assert created.status_code == 200
        project_id = created.json()["id"]
        assert created.json()["members"] == ["陈岩", "李明"]

        # A project created before execution-team input became mandatory can
        # still be listed and opened; it is prompted for the team on editing.
        project = db.get(ManagedProject, project_id)
        project.members_json = '["项目经理"]'
        db.commit()
        assert client.get(f"/v1/pm/projects/{project_id}").json()["members"] == []
        listed = client.get("/v1/pm/projects").json()["items"]
        assert next(item for item in listed if item["id"] == project_id)["members"] == []

        without_team = client.patch(
            f"/v1/pm/projects/{project_id}",
            json={
                "name": base_form["name"],
                "company_name": base_form["company_name"],
                "client": base_form["client"],
                "business_category": base_form["business_category"],
                "planned_start": base_form["planned_start"],
                "planned_end": base_form["planned_end"],
                "objective": base_form["objective"],
                "contract_amount": 0,
                "budget_revenue": 0,
                "budget_cost": 0,
            },
        )
        assert without_team.status_code == 422

        manager_only_update = client.patch(
            f"/v1/pm/projects/{project_id}",
            json={
                "name": base_form["name"],
                "company_name": base_form["company_name"],
                "client": base_form["client"],
                "business_category": base_form["business_category"],
                "members": [" 项目经理 "],
                "planned_start": base_form["planned_start"],
                "planned_end": base_form["planned_end"],
                "objective": base_form["objective"],
                "contract_amount": 0,
                "budget_revenue": 0,
                "budget_cost": 0,
            },
        )
        assert manager_only_update.status_code == 422

        updated = client.patch(
            f"/v1/pm/projects/{project_id}",
            json={
                "name": base_form["name"],
                "company_name": base_form["company_name"],
                "client": base_form["client"],
                "business_category": base_form["business_category"],
                "members": [" 执行甲 ", "执行乙", "执行甲"],
                "planned_start": base_form["planned_start"],
                "planned_end": base_form["planned_end"],
                "objective": base_form["objective"],
                "contract_amount": 0,
                "budget_revenue": 0,
                "budget_cost": 0,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["members"] == ["执行甲", "执行乙"]

        app.dependency_overrides[current_user] = lambda: users["second_business"]
        assert client.get(f"/v1/pm/projects/{project_id}").status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_project_budget_tax_create_update_margin_and_legacy_default(
    tmp_path, monkeypatch
) -> None:
    db, users = _database()
    client = _configure(monkeypatch, tmp_path, db, users["business"])
    base_form = {
        "project_no": "JADJ-Cc26A7",
        "name": "项目税费测试",
        "company_name": "京奥电竞（北京）科技有限公司",
        "client": "测试客户",
        "business_category": "电竞培训",
        "planned_start": "2026-08-01",
        "planned_end": "2026-09-01",
        "objective": "验证项目预算税费、预计毛利与旧客户端默认值。",
        "members_json": '["执行成员"]',
        "budget_revenue": "100000",
        "budget_cost": "60000",
    }
    try:
        # Old clients do not send budget_tax; both the API and persisted row
        # must safely treat it as zero.
        created = client.post("/v1/pm/projects", data=base_form)
        assert created.status_code == 200
        project_id = created.json()["id"]
        assert Decimal(str(created.json()["budget_tax"])) == Decimal("0")
        assert Decimal(str(created.json()["expected_margin"])) == Decimal("40000")
        assert db.get(ManagedProject, project_id).budget_tax == Decimal("0")

        updated = client.patch(
            f"/v1/pm/projects/{project_id}",
            json={
                "name": base_form["name"],
                "company_name": base_form["company_name"],
                "client": base_form["client"],
                "business_category": base_form["business_category"],
                "members": ["执行成员"],
                "planned_start": base_form["planned_start"],
                "planned_end": base_form["planned_end"],
                "objective": base_form["objective"],
                "contract_amount": 100000,
                "budget_revenue": 100000,
                "budget_cost": 60000,
                "budget_tax": 8000,
            },
        )
        assert updated.status_code == 200
        assert Decimal(str(updated.json()["budget_tax"])) == Decimal("8000")
        assert Decimal(str(updated.json()["expected_margin"])) == Decimal("32000")
        assert db.get(ManagedProject, project_id).budget_tax == Decimal("8000")

        negative_update = client.patch(
            f"/v1/pm/projects/{project_id}",
            json={
                "name": base_form["name"],
                "company_name": base_form["company_name"],
                "client": base_form["client"],
                "business_category": base_form["business_category"],
                "members": ["执行成员"],
                "planned_start": base_form["planned_start"],
                "planned_end": base_form["planned_end"],
                "objective": base_form["objective"],
                "budget_tax": -1,
            },
        )
        assert negative_update.status_code == 422
        assert db.get(ManagedProject, project_id).budget_tax == Decimal("8000")

        # Multipart form values are normalized before persistence, matching
        # the other project budget fields and preventing negative tax data.
        negative_create = client.post(
            "/v1/pm/projects",
            data={
                **base_form,
                "project_no": "JADJ-Cc26A8",
                "name": "负税费输入测试",
                "budget_tax": "-100",
            },
        )
        assert negative_create.status_code == 200
        assert Decimal(str(negative_create.json()["budget_tax"])) == Decimal("0")
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_project_client_contact_create_update_and_legacy_compatibility(
    tmp_path, monkeypatch
) -> None:
    db, users = _database()
    client = _configure(monkeypatch, tmp_path, db, users["business"])
    base_form = {
        "project_no": "JADJ-Cc26A9",
        "name": "Client contact test",
        "company_name": "京奥电竞（北京）科技有限公司",
        "client": "TJ Sports",
        "business_category": "Esports training",
        "planned_start": "2026-08-01",
        "planned_end": "2026-09-01",
        "objective": "Verify client company and contact are stored separately.",
        "members_json": '["Execution member"]',
    }
    try:
        # Historical/older Web clients do not send the new field.
        created = client.post("/v1/pm/projects", data=base_form)
        assert created.status_code == 200
        project_id = created.json()["id"]
        assert created.json()["client"] == "TJ Sports"
        assert created.json()["client_contact"] == ""
        assert db.get(ManagedProject, project_id).client_contact == ""

        update_payload = {
            "name": base_form["name"],
            "company_name": base_form["company_name"],
            "client": base_form["client"],
            "client_contact": "  Zhang San / Li Si  ",
            "business_category": base_form["business_category"],
            "members": ["Execution member"],
            "planned_start": base_form["planned_start"],
            "planned_end": base_form["planned_end"],
            "objective": base_form["objective"],
        }
        updated = client.patch(
            f"/v1/pm/projects/{project_id}", json=update_payload
        )
        assert updated.status_code == 200
        assert updated.json()["client_contact"] == "Zhang San / Li Si"
        assert db.get(ManagedProject, project_id).client_contact == "Zhang San / Li Si"

        # PATCH requests from a stale client must not erase a stored contact.
        update_payload.pop("client_contact")
        legacy_update = client.patch(
            f"/v1/pm/projects/{project_id}", json=update_payload
        )
        assert legacy_update.status_code == 200
        assert legacy_update.json()["client_contact"] == "Zhang San / Li Si"

        too_long_update = client.patch(
            f"/v1/pm/projects/{project_id}",
            json={**update_payload, "client_contact": "x" * 241},
        )
        assert too_long_update.status_code == 422
        assert db.get(ManagedProject, project_id).client_contact == "Zhang San / Li Si"

        too_long_create = client.post(
            "/v1/pm/projects",
            data={**base_form, "name": "Too long contact", "client_contact": "x" * 241},
        )
        assert too_long_create.status_code == 422
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_project_contract_status_and_post_start_warning(
    tmp_path, monkeypatch
) -> None:
    db, users = _database()
    client = _configure(monkeypatch, tmp_path, db, users["business"])
    base_form = {
        "project_no": "JADJ-Cc26B1",
        "name": "合同状态预警项目",
        "company_name": "京奥电竞（北京）科技有限公司",
        "client": "测试甲方",
        "business_category": "电竞培训",
        "planned_start": "2026-08-01",
        "planned_end": "2026-09-30",
        "objective": "验证项目启动后的合同签署预警。",
        "members_json": '["执行成员"]',
    }
    update_payload = {
        "name": base_form["name"],
        "company_name": base_form["company_name"],
        "client": base_form["client"],
        "business_category": base_form["business_category"],
        "members": ["执行成员"],
        "planned_start": base_form["planned_start"],
        "planned_end": base_form["planned_end"],
        "objective": base_form["objective"],
    }
    try:
        # Older clients omit the field. Existing and newly-created projects
        # safely default to unsigned, but pipeline projects do not warn yet.
        created = client.post("/v1/pm/projects", data=base_form)
        assert created.status_code == 200
        project_id = created.json()["id"]
        assert created.json()["contract_status"] == "unsigned"
        assert created.json()["contract_status_label"] == "未签署"
        assert created.json()["contract_unsigned_alert"] is False
        assert created.json()["contract_alert_message"] is None
        assert db.get(ManagedProject, project_id).contract_status == "unsigned"

        full_update_signed = client.patch(
            f"/v1/pm/projects/{project_id}",
            json={**update_payload, "contract_status": "signed_received"},
        )
        assert full_update_signed.status_code == 200
        assert full_update_signed.json()["contract_status"] == "signed_received"
        full_update_unsigned = client.patch(
            f"/v1/pm/projects/{project_id}",
            json={**update_payload, "contract_status": "unsigned"},
        )
        assert full_update_unsigned.status_code == 200
        assert full_update_unsigned.json()["contract_status"] == "unsigned"

        submitted = client.post(f"/v1/pm/projects/{project_id}/submit-initiation")
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "initiation_review"
        assert submitted.json()["contract_unsigned_alert"] is False

        app.dependency_overrides[current_user] = lambda: users["founder"]
        approved = _review(client, project_id, "initiation")
        assert approved.status_code == 200
        assert approved.json()["status"] == "active"
        assert approved.json()["contract_alert"] is True
        assert approved.json()["contract_unsigned_alert"] is True
        assert approved.json()["contract_alert_message"] == (
            "项目已启动，合同仍未签署收件"
        )

        # The project manager can record receipt after launch and the
        # deterministic warning clears immediately.
        app.dependency_overrides[current_user] = lambda: users["business"]
        signed = client.patch(
            f"/v1/pm/projects/{project_id}/contract-status",
            json={"contract_status": "signed_received"},
        )
        assert signed.status_code == 200
        assert signed.json()["contract_status"] == "signed_received"
        assert signed.json()["contract_status_label"] == "已签署收件"
        assert signed.json()["contract_alert"] is False
        assert signed.json()["contract_unsigned_alert"] is False
        assert signed.json()["contract_alert_message"] is None
        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "pm_contract_status_update")
            .order_by(AuditLog.created_at.desc())
        )
        assert audit is not None
        assert '"previous_status": "unsigned"' in audit.details_json
        assert '"contract_status": "signed_received"' in audit.details_json

        # A stale client that omits the field must not reset a signed project.
        legacy_update = client.patch(
            f"/v1/pm/projects/{project_id}", json=update_payload
        )
        assert legacy_update.status_code == 200
        assert legacy_update.json()["contract_status"] == "signed_received"

        # Contract warnings remain valid in every state after startup, and
        # the lightweight endpoint remains available after archival without
        # reopening the rest of the project for edits.
        project = db.get(ManagedProject, project_id)
        for post_start_status in (
            "active", "closing_review", "closing_rejected", "closed", "archived",
        ):
            project.status = post_start_status
            project.contract_status = "unsigned"
            db.commit()
            post_start_payload = client.get(
                f"/v1/pm/projects/{project_id}"
            ).json()
            assert post_start_payload["contract_alert"] is True
            assert post_start_payload["contract_alert_message"] == (
                "项目已启动，合同仍未签署收件"
            )
        signed_after_archive = client.patch(
            f"/v1/pm/projects/{project_id}/contract-status",
            json={"contract_status": "signed_received"},
        )
        assert signed_after_archive.status_code == 200
        assert signed_after_archive.json()["status"] == "archived"
        assert signed_after_archive.json()["contract_alert"] is False

        # Visibility and ownership remain enforced on the lightweight route:
        # privileged viewers can see the project but cannot mutate a PM field,
        # while another PM receives a non-disclosing 404.
        app.dependency_overrides[current_user] = lambda: users["finance"]
        assert client.patch(
            f"/v1/pm/projects/{project_id}/contract-status",
            json={"contract_status": "unsigned"},
        ).status_code == 403
        app.dependency_overrides[current_user] = lambda: users["founder"]
        assert client.patch(
            f"/v1/pm/projects/{project_id}/contract-status",
            json={"contract_status": "unsigned"},
        ).status_code == 403
        app.dependency_overrides[current_user] = lambda: users["second_business"]
        assert client.patch(
            f"/v1/pm/projects/{project_id}/contract-status",
            json={"contract_status": "unsigned"},
        ).status_code == 404
        app.dependency_overrides[current_user] = lambda: users["business"]

        invalid_update = client.patch(
            f"/v1/pm/projects/{project_id}/contract-status",
            json={"contract_status": "unknown"},
        )
        assert invalid_update.status_code == 422
        assert db.get(ManagedProject, project_id).contract_status == "signed_received"

        invalid_create = client.post(
            "/v1/pm/projects",
            data={**base_form, "name": "非法状态", "contract_status": "unknown"},
        )
        assert invalid_create.status_code == 422
        signed_create = client.post(
            "/v1/pm/projects",
            data={
                **base_form,
                "project_no": "JADJ-Cc26B2",
                "name": "已收件立项",
                "contract_status": "signed_received",
            },
        )
        assert signed_create.status_code == 200
        assert signed_create.json()["contract_status"] == "signed_received"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_manual_project_number_validation_duplicate_and_attachment_cleanup(
    tmp_path, monkeypatch
) -> None:
    db, users = _database()
    client = _configure(monkeypatch, tmp_path, db, users["business"])
    base_form = {
        "project_no": "  FEISHU_2026-A  ",
        "name": "飞书项目段测试",
        "company_name": "京奥电竞（北京）科技有限公司",
        "client": "测试甲方",
        "business_category": "电竞培训",
        "planned_start": "2026-08-01",
        "planned_end": "2026-09-30",
        "objective": "验证项目经理填写的飞书项目段可安全落到附件目录。",
        "members_json": '["执行成员"]',
    }
    try:
        created = client.post(
            "/v1/pm/projects",
            data=base_form,
            files={
                "proposal_file": (
                    "立项方案.pdf", b"first-file", "application/pdf"
                )
            },
        )
        assert created.status_code == 200
        assert created.json()["project_no"] == "FEISHU_2026-A"
        project_id = created.json()["id"]
        stored = db.get(ManagedProject, project_id)
        assert stored.project_no == "FEISHU_2026-A"
        assert "FEISHU_2026-A" in stored.proposal_path

        # A repeated Feishu segment is rejected before another attachment is
        # written, while the original project and file remain untouched.
        files_before = sorted(
            path for path in (tmp_path / "knowledge").rglob("*") if path.is_file()
        )
        duplicate = client.post(
            "/v1/pm/projects",
            data={**base_form, "project_no": "FEISHU_2026-A", "name": "重复项目"},
            files={
                "proposal_file": (
                    "重复方案.pdf", b"duplicate-file", "application/pdf"
                )
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "项目编号已存在，请核对飞书项目段"
        assert sorted(
            path for path in (tmp_path / "knowledge").rglob("*") if path.is_file()
        ) == files_before

        for invalid_number in (
            "A",
            "A" * 41,
            "../secret",
            "项目一号",
            "AA BB",
        ):
            invalid = client.post(
                "/v1/pm/projects",
                data={**base_form, "project_no": invalid_number},
            )
            assert invalid.status_code == 422
        missing_number = client.post(
            "/v1/pm/projects",
            data={key: value for key, value in base_form.items() if key != "project_no"},
        )
        assert missing_number.status_code == 422

        # Simulate the narrow concurrency race after file writing. The
        # database unique constraint wins and the just-written orphan is
        # removed before returning the friendly conflict response.
        original_flush = db.flush

        def duplicate_flush(*args, **kwargs):
            if any(isinstance(item, ManagedProject) for item in db.new):
                raise IntegrityError(
                    "INSERT managed_projects", {}, Exception("duplicate")
                )
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(db, "flush", duplicate_flush)
        raced = client.post(
            "/v1/pm/projects",
            data={**base_form, "project_no": "FEISHU_2026-RACE"},
            files={
                "proposal_file": (
                    "并发方案.pdf", b"race-file", "application/pdf"
                )
            },
        )
        assert raced.status_code == 409
        assert sorted(
            path for path in (tmp_path / "knowledge").rglob("*") if path.is_file()
        ) == files_before
    finally:
        app.dependency_overrides.clear()
        db.close()
