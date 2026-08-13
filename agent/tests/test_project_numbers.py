from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, ManagedProject, ProjectNumberSequence, User
from app.project_numbers import (
    allocate_project_number,
    format_project_number,
    migrate_existing_project_numbers,
    project_number_year,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _user(db: Session) -> User:
    user = User(
        username="number-test",
        display_name="Number Test",
        password_hash="x",
        role="employee",
        organization_role="business",
        confidentiality_ceiling="L3",
    )
    db.add(user)
    db.flush()
    return user


def _project(db: Session, user: User, *, number: str, created_at: datetime) -> ManagedProject:
    item = ManagedProject(
        project_no=number,
        name=number,
        company_name="Jingao",
        client="Client",
        business_category="Training",
        manager_user_id=user.id,
        members_json='["Member"]',
        planned_start=created_at.date(),
        planned_end=created_at.date(),
        objective="Test project objective",
        created_by_user_id=user.id,
        created_at=created_at,
    )
    db.add(item)
    db.flush()
    return item


def test_format_project_number_boundaries_and_shanghai_year() -> None:
    assert format_project_number(2026, 1) == "JADJ-Cc2601"
    assert format_project_number(2026, 9) == "JADJ-Cc2609"
    assert format_project_number(2026, 10) == "JADJ-Cc2610"
    assert format_project_number(2026, 99) == "JADJ-Cc2699"
    assert format_project_number(2026, 100) == "JADJ-Cc26100"
    with pytest.raises(ValueError):
        format_project_number(2026, 101)
    # 16:30 UTC is already the following calendar year in Beijing.
    assert project_number_year(datetime(2026, 12, 31, 16, 30, tzinfo=timezone.utc)) == 2027


def test_allocator_is_sequential_and_rejects_project_101() -> None:
    engine = _engine()
    with Session(engine) as db:
        assert allocate_project_number(db, year=2026) == "JADJ-Cc2601"
        assert allocate_project_number(db, year=2026) == "JADJ-Cc2602"
        db.get(ProjectNumberSequence, 2026).last_value = 99
        db.flush()
        assert allocate_project_number(db, year=2026) == "JADJ-Cc26100"
        with pytest.raises(HTTPException) as exc:
            allocate_project_number(db, year=2026)
        assert exc.value.status_code == 409


def test_legacy_migration_is_stable_and_idempotent() -> None:
    engine = _engine()
    with Session(engine) as db:
        user = _user(db)
        first = _project(
            db,
            user,
            number="JADJ-2026-0001",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        second = _project(
            db,
            user,
            number="JADJ-2026-0002",
            created_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
        )
        db.commit()

    with engine.begin() as connection:
        assert migrate_existing_project_numbers(connection) == 2
    with Session(engine) as db:
        values = db.scalars(
            select(ManagedProject.project_no).order_by(ManagedProject.created_at)
        ).all()
        assert values == ["JADJ-Cc2601", "JADJ-Cc2602"]
        assert db.get(ProjectNumberSequence, 2026).last_value == 2

    with engine.begin() as connection:
        assert migrate_existing_project_numbers(connection) == 0
    with Session(engine) as db:
        assert allocate_project_number(db, year=2026) == "JADJ-Cc2603"
