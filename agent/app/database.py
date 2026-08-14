from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_database() -> None:
    if settings.database_url.startswith("postgresql"):
        with engine.begin() as connection:
            # All long-running workers start together under Compose.  Serialize
            # the first schema creation so concurrent CREATE TABLE statements
            # cannot race in PostgreSQL's system catalog.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": 740_586_061_319},
            )
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            Base.metadata.create_all(bind=connection)
            connection.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                    "organization_role VARCHAR(40)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                    "project_delete_password_hash TEXT"
                )
            )
            # ``create_all`` cannot add columns to a table that already
            # exists. Keep additive migrations inside the same advisory
            # transaction so older NAS installations are upgraded once,
            # before any API worker begins serving requests.
            connection.execute(
                text(
                    "ALTER TABLE managed_projects ADD COLUMN IF NOT EXISTS "
                    "budget_tax NUMERIC(18, 2) NOT NULL DEFAULT 0"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE managed_projects ADD COLUMN IF NOT EXISTS "
                    "process_received NUMERIC(18, 2) NOT NULL DEFAULT 0"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE managed_projects ADD COLUMN IF NOT EXISTS "
                    "process_spent NUMERIC(18, 2) NOT NULL DEFAULT 0"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE managed_projects ADD COLUMN IF NOT EXISTS "
                    "process_advanced NUMERIC(18, 2) NOT NULL DEFAULT 0"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE managed_projects ADD COLUMN IF NOT EXISTS "
                    "process_finance_updated_at TIMESTAMPTZ"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE managed_projects ADD COLUMN IF NOT EXISTS "
                    "client_contact VARCHAR(240) NOT NULL DEFAULT ''"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE managed_projects ADD COLUMN IF NOT EXISTS "
                    "contract_status VARCHAR(32) NOT NULL DEFAULT 'unsigned'"
                )
            )
            # Normalize unexpected legacy values before adding the database
            # constraint.  This keeps the additive migration idempotent on
            # installations that may have trial data from an earlier build.
            connection.execute(
                text(
                    "UPDATE managed_projects SET contract_status = 'unsigned' "
                    "WHERE contract_status IS NULL "
                    "OR contract_status NOT IN ('unsigned', 'signed_received')"
                )
            )
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = 'ck_managed_projects_contract_status'
                        ) THEN
                            ALTER TABLE managed_projects
                            ADD CONSTRAINT ck_managed_projects_contract_status
                            CHECK (contract_status IN ('unsigned', 'signed_received'));
                        END IF;
                    END
                    $$
                    """
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS "
                    "counterparty_account_hash VARCHAR(64)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS "
                    "project_reference VARCHAR(80)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS "
                    "internal_transfer_status VARCHAR(24) NOT NULL DEFAULT 'unreviewed'"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS "
                    "internal_transfer_source VARCHAR(40)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS "
                    "internal_transfer_counterparty_entity_id VARCHAR(36) "
                    "REFERENCES business_entities(id)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS "
                    "internal_transfer_reviewed_by_user_id VARCHAR(36) REFERENCES users(id)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE bank_transactions ADD COLUMN IF NOT EXISTS "
                    "internal_transfer_reviewed_at TIMESTAMPTZ"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_bank_transactions_counterparty_account_hash "
                    "ON bank_transactions (counterparty_account_hash)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_bank_transactions_project_reference "
                    "ON bank_transactions (project_reference)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_bank_transactions_internal_transfer_status "
                    "ON bank_transactions (internal_transfer_status)"
                )
            )
            # Project numbers are entered by the PM to match the existing
            # Feishu project segment. Existing issued numbers stay unchanged;
            # only enforce a filesystem-safe, portable character set.
            connection.execute(
                text(
                    "ALTER TABLE managed_projects DROP CONSTRAINT IF EXISTS "
                    "ck_managed_projects_project_no_cc_format"
                )
            )
            connection.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = 'ck_managed_projects_project_no_safe_format'
                        ) THEN
                            ALTER TABLE managed_projects
                            ADD CONSTRAINT ck_managed_projects_project_no_safe_format
                            CHECK (
                                project_no ~ '^[A-Za-z0-9_-]{2,40}$'
                            );
                        END IF;
                    END
                    $$
                    """
                )
            )
        return
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
