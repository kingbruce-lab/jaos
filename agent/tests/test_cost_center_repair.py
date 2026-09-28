"""Regression coverage for the B05/B06 data repair; isolated SQLite only."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, String, Numeric
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
import repair_cost_centers_20260929 as migration


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(primary_key=True)
    project_no: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    status: Mapped[str] = mapped_column(default="active")
    entity_id: Mapped[str]


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(primary_key=True)
    project_reference: Mapped[str]
    pm_project_id: Mapped[str | None]
    entity_id: Mapped[str]
    expense: Mapped[float] = mapped_column(Numeric(18, 2))
    summary: Mapped[str]


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(migration, "ManagedProject", Project)
    monkeypatch.setattr(migration, "BankTransaction", Transaction)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Project(id="delta", project_no="CC26B05", name="三角洲国际战队培训", entity_id="ja"),
            Project(id="support", project_no="CC26B06", name="后勤保障项目", entity_id="ja"),
            Transaction(id="expense", project_reference="Cc26B05", pm_project_id="delta",
                        entity_id="ja", expense=130248, summary="原始银行摘要"),
            Transaction(id="delta-expense", project_reference="CC26B06", pm_project_id="support",
                        entity_id="ja", expense=100, summary="三角洲支出"),
        ])
        session.commit()
        yield session


def test_preview_apply_and_idempotency(db):
    plan = migration.repair(db)
    assert len(plan["project_codes"]) == len(plan["transaction_links"]) == 2
    assert db.get(Project, "delta").project_no == "CC26B05"
    assert migration.repair(db, apply=True) == plan
    db.commit()
    assert db.get(Project, "delta").project_no == "CC26B06"
    assert db.get(Project, "support").project_no == "CC26B05"
    tx = db.get(Transaction, "expense")
    assert tx.pm_project_id == "support"
    assert tx.expense == 130248
    assert tx.project_reference == "Cc26B05"
    assert tx.summary == "原始银行摘要"
    assert db.get(Transaction, "delta-expense").pm_project_id == "delta"
    assert migration.repair(db, apply=True) == {"project_codes": [], "transaction_links": []}


def test_unknown_name_aborts(db):
    db.get(Project, "delta").name = "未知项目"
    db.flush()
    with pytest.raises(ValueError, match="人工核对"):
        migration.repair(db, apply=True)
    assert db.get(Project, "support").project_no == "CC26B06"


def test_cross_company_aborts(db):
    db.get(Transaction, "expense").entity_id = "other"
    db.flush()
    with pytest.raises(ValueError, match="公司不一致"):
        migration.repair(db, apply=True)
    assert db.get(Project, "delta").project_no == "CC26B05"


def test_conflicting_source_code_aborts(db):
    db.get(Transaction, "expense").project_reference = "CC26B07"
    db.flush()
    with pytest.raises(ValueError, match="冲突"):
        migration.repair(db, apply=True)


def test_missing_project_unlinks_without_changing_bank_code(db):
    db.delete(db.get(Project, "support"))
    db.flush()
    migration.repair(db, apply=True)
    assert db.get(Transaction, "expense").pm_project_id is None
    assert db.get(Transaction, "expense").project_reference == "Cc26B05"
