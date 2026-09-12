from __future__ import annotations

from app import database


class RecordingConnection:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(str(statement))


class CurrentSchema:
    def get_columns(self, table):
        return [{"name": name} for name in database.ADDITIVE_COLUMNS[table]]

    def get_check_constraints(self, table):
        assert table == "managed_projects"
        return [{"name": name} for name in (
            "ck_managed_projects_contract_status",
            "ck_managed_projects_project_no_safe_format",
        )]

    def get_indexes(self, table):
        assert table == "bank_transactions"
        return [{"name": name} for name in database.ADDITIVE_INDEXES]


def test_current_schema_runs_no_ddl_or_updates(monkeypatch):
    connection = RecordingConnection()
    monkeypatch.setattr(database, "inspect", lambda _: CurrentSchema())
    database._apply_postgresql_migrations(connection)
    assert connection.statements == []


def test_migration_adds_only_missing_column(monkeypatch):
    class MissingOwner(CurrentSchema):
        def get_columns(self, table):
            return [row for row in super().get_columns(table) if row["name"] != "source_owner_name"]

    connection = RecordingConnection()
    monkeypatch.setattr(database, "inspect", lambda _: MissingOwner())
    database._apply_postgresql_migrations(connection)
    assert connection.statements == [
        "ALTER TABLE file_blobs ADD COLUMN source_owner_name VARCHAR(120)"
    ]


def test_legacy_constraints_migrate_without_rewriting_existing_codes(monkeypatch):
    class LegacySchema(CurrentSchema):
        def get_check_constraints(self, table):
            return [{"name": "ck_managed_projects_project_no_cc_format"}]

    connection = RecordingConnection()
    monkeypatch.setattr(database, "inspect", lambda _: LegacySchema())
    database._apply_postgresql_migrations(connection)
    statements = "\n".join(connection.statements)
    assert "DROP CONSTRAINT ck_managed_projects_project_no_cc_format" in statements
    assert "ADD CONSTRAINT ck_managed_projects_project_no_safe_format" in statements
    assert "ADD CONSTRAINT ck_managed_projects_contract_status" in statements
    assert "SET project_no" not in statements
