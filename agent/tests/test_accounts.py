from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import OperationalError, TimeoutError as DatabasePoolTimeout
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import (
    authenticate,
    bootstrap_admin,
    create_session,
    current_user,
    hash_password,
    login_rate_limiter,
)
from app.database import get_db
from app.main import app
from app.models import AuditLog, Base, KnowledgeCategory, SessionToken, User


def account_db() -> tuple[Session, User, User]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    founder = User(
        username="founder",
        display_name="Founder",
        password_hash=hash_password("Founder-Test-Password-2026"),
        role="founder",
        organization_role=None,
        confidentiality_ceiling="L4",
    )
    employee = User(
        username="employee",
        display_name="Employee",
        password_hash=hash_password("Employee-Test-Password-2026"),
        role="employee",
        organization_role=None,
        confidentiality_ceiling="L2",
    )
    db.add_all([
        founder,
        employee,
        KnowledgeCategory(key="training", name="电竞培训", active=True),
    ])
    db.commit()
    return db, founder, employee


@pytest.mark.parametrize("failure", [
    DatabasePoolTimeout("private connection details"),
    OperationalError("SELECT secret", {"password": "private"}, Exception("lock timeout")),
])
def test_login_database_errors_are_retryable_and_do_not_expose_details(failure):
    def unavailable_db():
        raise failure
        yield

    app.dependency_overrides[get_db] = unavailable_db
    try:
        response = TestClient(app).post("/v1/auth/login", json={
            "username": "founder", "password": "No-Authentication-Attempt",
        })
        assert response.status_code == 503
        assert response.headers["retry-after"] == "5"
        assert "无需更改密码" in response.json()["detail"]
        assert "private" not in response.text
        assert "SELECT" not in response.text
    finally:
        app.dependency_overrides.clear()


def configure_overrides(db: Session, actor: User) -> None:
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: actor


def test_existing_founder_is_migrated_to_l5_with_audit() -> None:
    db, founder, employee = account_db()
    try:
        bootstrap_admin(db)
        db.refresh(founder)
        db.refresh(employee)
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "founder_l5_policy_migration"
            )
        )

        assert founder.confidentiality_ceiling == "L5"
        assert founder.organization_role == "management"
        assert employee.confidentiality_ceiling == "L2"
        assert employee.organization_role == "business"
        assert audit is not None
        assert audit.user_id == founder.id
    finally:
        db.close()


def test_named_ceo_is_migrated_to_management_l5_contract_access_once() -> None:
    db, _founder, _employee = account_db()
    ceo = User(
        username="jaanliyuan",
        display_name="安利园",
        password_hash=hash_password("Ceo-Test-Password-2026"),
        role="employee",
        organization_role="business",
        confidentiality_ceiling="L3",
        departments_json='["training"]',
    )
    db.add(ceo)
    db.commit()
    try:
        bootstrap_admin(db)
        db.refresh(ceo)
        first_audits = db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "ceo_l5_contract_access_v1"
            )
        )

        assert ceo.organization_role == "management"
        assert ceo.confidentiality_ceiling == "L5"
        assert ceo.departments_json == '["*"]'
        assert first_audits == 1

        bootstrap_admin(db)
        second_audits = db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "ceo_l5_contract_access_v1"
            )
        )
        assert second_audits == 1
    finally:
        db.close()


def test_founder_creates_account_without_exposing_password_hash() -> None:
    db, founder, _employee = account_db()
    configure_overrides(db, founder)
    try:
        response = TestClient(app).post(
            "/v1/admin/users",
            json={
                "username": "Planner.One",
                "display_name": "员工一",
                "password": "Planner-Initial-Password-2026",
                "role": "business",
                "confidentiality_ceiling": "L2",
                "departments": ["training"],
            },
        )
        payload = response.json()
        created = db.scalar(
            select(User).where(User.username == "planner.one")
        )
        audit = db.scalar(
            select(AuditLog).where(AuditLog.action == "create_local_user")
        )

        assert response.status_code == 200
        assert payload["username"] == "planner.one"
        assert payload["organization_role"] == "business"
        assert "password_hash" not in payload
        assert created is not None
        assert authenticate(
            db,
            "planner.one",
            "Planner-Initial-Password-2026",
        ) is not None
        assert audit is not None
        assert "Planner-Initial-Password-2026" not in audit.details_json
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_password_policy_accepts_eight_characters_and_rejects_seven() -> None:
    db, founder, employee = account_db()
    configure_overrides(db, founder)
    try:
        client = TestClient(app)
        accepted_create = client.post(
            "/v1/admin/users",
            json={
                "username": "eightchars",
                "display_name": "八位密码测试",
                "password": "abcd1234",
                "role": "business",
                "confidentiality_ceiling": "L1",
            },
        )
        rejected_create = client.post(
            "/v1/admin/users",
            json={
                "username": "sevenchars",
                "display_name": "七位密码测试",
                "password": "abc1234",
                "role": "business",
                "confidentiality_ceiling": "L1",
            },
        )
        accepted_reset = client.post(
            f"/v1/admin/users/{employee.id}/password",
            json={"password": "reset123"},
        )
        rejected_reset = client.post(
            f"/v1/admin/users/{employee.id}/password",
            json={"password": "reset12"},
        )
        accepted_own_change = client.post(
            "/v1/me/password",
            json={
                "current_password": "Founder-Test-Password-2026",
                "new_password": "owner123",
            },
        )

        assert accepted_create.status_code == 200
        assert rejected_create.status_code == 422
        assert accepted_reset.status_code == 200
        assert rejected_reset.status_code == 422
        assert accepted_own_change.status_code == 200
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_account_role_options_reject_removed_planner_role() -> None:
    db, founder, _employee = account_db()
    configure_overrides(db, founder)
    try:
        response = TestClient(app).post(
            "/v1/admin/users",
            json={
                "username": "legacy.planner",
                "display_name": "旧策划角色",
                "password": "password",
                "role": "planner",
                "confidentiality_ceiling": "L2",
            },
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_non_founder_cannot_manage_accounts() -> None:
    db, _founder, employee = account_db()
    configure_overrides(db, employee)
    try:
        response = TestClient(app).get("/v1/admin/users")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_deactivation_revokes_sessions_and_last_manager_is_protected() -> None:
    db, founder, employee = account_db()
    create_session(db, employee)
    configure_overrides(db, founder)
    try:
        client = TestClient(app)
        response = client.patch(
            f"/v1/admin/users/{employee.id}",
            json={"active": False},
        )
        founder_response = client.patch(
            f"/v1/admin/users/{founder.id}",
            json={"active": False},
        )
        session_count = db.scalar(
            select(func.count(SessionToken.id)).where(
                SessionToken.user_id == employee.id
            )
        )

        assert response.status_code == 200
        assert response.json()["active"] is False
        assert session_count == 0
        assert authenticate(
            db,
            employee.username,
            "Employee-Test-Password-2026",
        ) is None
        assert founder_response.status_code == 409
        assert "最后一个启用的管理账号" in founder_response.json()["detail"]
        assert founder.active is True
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_manager_can_be_adjusted_and_deactivated_when_another_manager_exists() -> None:
    db, founder, _employee = account_db()
    second_manager = User(
        username="manager-two",
        display_name="第二管理账号",
        password_hash=hash_password("Manager-Two-Password-2026"),
        role="founder",
        organization_role="management",
        confidentiality_ceiling="L5",
        active=True,
    )
    db.add(second_manager)
    db.commit()
    configure_overrides(db, second_manager)
    try:
        client = TestClient(app)
        adjusted = client.patch(
            f"/v1/admin/users/{founder.id}",
            json={
                "role": "business",
                "confidentiality_ceiling": "L2",
            },
        )
        deactivated = client.patch(
            f"/v1/admin/users/{founder.id}",
            json={"active": False},
        )
        reset = client.post(
            f"/v1/admin/users/{second_manager.id}/password",
            json={"password": "Manager-New-Password"},
        )

        assert adjusted.status_code == 200
        assert adjusted.json()["organization_role"] == "business"
        assert adjusted.json()["confidentiality_ceiling"] == "L2"
        assert deactivated.status_code == 200
        assert deactivated.json()["active"] is False
        assert reset.status_code == 200
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_own_password_change_revokes_all_sessions() -> None:
    db, founder, _employee = account_db()
    create_session(db, founder)
    configure_overrides(db, founder)
    try:
        response = TestClient(app).post(
            "/v1/me/password",
            json={
                "current_password": "Founder-Test-Password-2026",
                "new_password": "Founder-New-Password-2026",
            },
        )
        session_count = db.scalar(
            select(func.count(SessionToken.id)).where(
                SessionToken.user_id == founder.id
            )
        )

        assert response.status_code == 200
        assert response.json()["login_required"] is True
        assert session_count == 0
        assert authenticate(
            db,
            founder.username,
            "Founder-Test-Password-2026",
        ) is None
        assert authenticate(
            db,
            founder.username,
            "Founder-New-Password-2026",
        ) is not None
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_employee_session_loads_workspace_without_admin_access() -> None:
    db, _founder, employee = account_db()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        login = client.post(
            "/v1/auth/login",
            json={
                "username": employee.username,
                "password": "Employee-Test-Password-2026",
            },
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        assert login.status_code == 200
        assert client.get("/v1/me", headers=headers).status_code == 200
        assert client.get("/v1/status", headers=headers).status_code == 200
        assert client.get("/v1/projects", headers=headers).status_code == 200
        assert client.get("/v1/review/queue", headers=headers).status_code == 403
        assert client.get("/v1/admin/users", headers=headers).status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_login_is_rate_limited_without_revealing_password_validity() -> None:
    db, founder, _employee = account_db()

    def override_db():
        yield db

    login_rate_limiter.reset()
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        statuses = [
            client.post(
                "/v1/auth/login",
                json={"username": founder.username, "password": "wrong-password"},
            ).status_code
            for _attempt in range(5)
        ]
        valid_while_locked = client.post(
            "/v1/auth/login",
            json={
                "username": founder.username,
                "password": "Founder-Test-Password-2026",
            },
        )
        failed_audits = db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "login_failed"
            )
        )

        assert statuses[:4] == [401, 401, 401, 401]
        assert statuses[4] == 429
        assert valid_while_locked.status_code == 429
        assert int(valid_while_locked.headers["retry-after"]) > 0
        assert failed_audits == 5
    finally:
        login_rate_limiter.reset()
        app.dependency_overrides.clear()
        db.close()
