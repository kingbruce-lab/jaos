from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
if settings.database_url.startswith("postgresql"):
    # Bound database lock waits, not file transfers or long Python operations.
    connect_args["options"] = "-c lock_timeout=5000"
engine = create_engine(
    settings.database_url, connect_args=connect_args, pool_pre_ping=True,
    **({"pool_timeout": 10} if settings.database_url.startswith("postgresql") else {}),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Trusted identifiers only. Even ADD COLUMN IF NOT EXISTS takes an exclusive
# table lock when the column already exists. Inspect first on every worker run.
ADDITIVE_COLUMNS = {
    "education_staff": {
        "active": "BOOLEAN NOT NULL DEFAULT TRUE",
        "note": "TEXT NOT NULL DEFAULT ''",
    },
    "education_cohorts": {
        "course_period": "VARCHAR(20) NOT NULL DEFAULT '1_month'",
        "deleted_at": "TIMESTAMPTZ",
    },
    "education_cash_entries": {
        "category": "VARCHAR(40) NOT NULL DEFAULT '其他'",
        "detail": "VARCHAR(80) NOT NULL DEFAULT '其他'",
        "staff_id": "VARCHAR(36)",
        "ended_on": "DATE",
    },
    "education_students": {
        "student_no": "VARCHAR(32)",
        "birth_date": "DATE",
        "guardian_name": "VARCHAR(80) NOT NULL DEFAULT ''",
        "guardian_phone": "VARCHAR(30) NOT NULL DEFAULT ''",
        "emergency_contact": "VARCHAR(240) NOT NULL DEFAULT ''",
        "health_notes": "TEXT NOT NULL DEFAULT ''",
        "referrer_name": "VARCHAR(120) NOT NULL DEFAULT ''",
        "referral_channel": "VARCHAR(160) NOT NULL DEFAULT ''",
        "game_account": "VARCHAR(100) NOT NULL DEFAULT ''",
        "current_rank": "VARCHAR(100) NOT NULL DEFAULT ''",
        "learning_status": "VARCHAR(24) NOT NULL DEFAULT '已报名'",
        "staff_assignments_json": "TEXT NOT NULL DEFAULT '[]'",
    },
    "education_cost_documents": {
        "ended_on": "DATE",
    },
    "education_schedule_days": {
        "report_json": "TEXT NOT NULL DEFAULT '{}'",
    },
    "users": {
        "organization_role": "VARCHAR(40)",
        "project_delete_password_hash": "TEXT",
    },
    "file_blobs": {
        "source_owner_name": "VARCHAR(120)",
        "source_owner_uid": "BIGINT",
    },
    "managed_projects": {
        "budget_tax": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "process_received": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "process_spent": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "process_advanced": "NUMERIC(18, 2) NOT NULL DEFAULT 0",
        "process_finance_updated_at": "TIMESTAMPTZ",
        "client_contact": "VARCHAR(240) NOT NULL DEFAULT ''",
        "contract_status": "VARCHAR(32) NOT NULL DEFAULT 'unsigned'",
    },
    "bank_transactions": {
        "counterparty_account_hash": "VARCHAR(64)",
        "project_reference": "VARCHAR(80)",
        "internal_transfer_status": "VARCHAR(24) NOT NULL DEFAULT 'unreviewed'",
        "internal_transfer_source": "VARCHAR(40)",
        "internal_transfer_counterparty_entity_id": "VARCHAR(36) REFERENCES business_entities(id)",
        "internal_transfer_reviewed_by_user_id": "VARCHAR(36) REFERENCES users(id)",
        "internal_transfer_reviewed_at": "TIMESTAMPTZ",
    },
}
ADDITIVE_INDEXES = {
    "ix_bank_transactions_counterparty_account_hash": "counterparty_account_hash",
    "ix_bank_transactions_project_reference": "project_reference",
    "ix_bank_transactions_internal_transfer_status": "internal_transfer_status",
}


def _apply_postgresql_migrations(connection: Connection) -> None:
    inspector = inspect(connection)
    for table, columns in ADDITIVE_COLUMNS.items():
        existing = {column["name"] for column in inspector.get_columns(table)}
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))

    constraints = {
        item["name"] for item in inspector.get_check_constraints("managed_projects")
    }
    if "ck_managed_projects_contract_status" not in constraints:
        connection.execute(text(
            "UPDATE managed_projects SET contract_status = 'unsigned' "
            "WHERE contract_status IS NULL "
            "OR contract_status NOT IN ('unsigned', 'signed_received')"
        ))
        connection.execute(text(
            "ALTER TABLE managed_projects ADD CONSTRAINT ck_managed_projects_contract_status "
            "CHECK (contract_status IN ('unsigned', 'signed_received'))"
        ))
    if "ck_managed_projects_project_no_cc_format" in constraints:
        connection.execute(text(
            "ALTER TABLE managed_projects DROP CONSTRAINT ck_managed_projects_project_no_cc_format"
        ))
    # API validation covers new codes; keep previously issued codes readable.
    if "ck_managed_projects_project_no_safe_format" not in constraints:
        connection.execute(text(
            "ALTER TABLE managed_projects ADD CONSTRAINT ck_managed_projects_project_no_safe_format "
            "CHECK (project_no ~ '^[A-Za-z0-9_-]{2,40}$')"
        ))
    existing_indexes = {
        item["name"] for item in inspector.get_indexes("bank_transactions")
    }
    for name, column in ADDITIVE_INDEXES.items():
        if name not in existing_indexes:
            connection.execute(text(f"CREATE INDEX {name} ON bank_transactions ({column})"))



def init_database() -> None:
    if settings.database_url.startswith("postgresql"):
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            # Serialize migrations, with bounded waits even for periodic CLI jobs.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": 740_586_061_319},
            )
            if not connection.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")):
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            Base.metadata.create_all(bind=connection)
            _apply_postgresql_migrations(connection)
        return
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
