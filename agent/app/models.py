from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class PortableVector(TypeDecorator):
    """Use pgvector on PostgreSQL and JSON text in the local SQLite test DB."""

    impl = Text
    cache_ok = True

    class comparator_factory(TypeDecorator.Comparator):
        def cosine_distance(self, other):
            """Expose pgvector cosine distance on PostgreSQL."""

            return self.op("<=>", return_type=Float)(other)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        values = [float(item) for item in value]
        if dialect.name == "postgresql":
            return values
        return json.dumps(values, separators=(",", ":"))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return [float(item) for item in json.loads(value)]
        return [float(item) for item in value]


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    # A separate second factor for founder-only project deletion.  This is
    # intentionally independent from the login password and is never exposed
    # by user/account payloads.
    project_delete_password_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    role: Mapped[str] = mapped_column(String(40), default="employee")
    # Organizational function is intentionally separate from application
    # privileges so finance/HR/project systems can reuse one account model.
    organization_role: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        default="business",
    )
    confidentiality_ceiling: Mapped[str] = mapped_column(String(2), default="L1")
    departments_json: Mapped[str] = mapped_column(Text, default='["training"]')
    external_identity: Mapped[str | None] = mapped_column(String(160), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BusinessEntity(Base):
    """A Jingao legal entity shared by finance and project management."""

    __tablename__ = "business_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(240), unique=True, index=True)
    short_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "bank_name",
            "account_number_hash",
            name="uq_financial_entity_bank_account",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("business_entities.id"), index=True)
    bank_name: Mapped[str] = mapped_column(String(160))
    account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_number_masked: Mapped[str] = mapped_column(String(80))
    account_number_hash: Mapped[str] = mapped_column(String(64), index=True)
    currency: Mapped[str] = mapped_column(String(12), default="CNY")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BankStatementBatch(Base):
    __tablename__ = "bank_statement_batches"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "file_hash",
            name="uq_statement_account_file",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("business_entities.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(300))
    source_path: Mapped[str] = mapped_column(Text)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    confirmed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "fingerprint",
            name="uq_bank_transaction_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("bank_statement_batches.id"), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey("business_entities.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    transacted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    income: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    expense: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    counterparty: Mapped[str | None] = mapped_column(String(300), nullable=True)
    counterparty_account_masked: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # The raw counterparty account number is never retained.  Its hash lets us
    # deterministically recognise transfers to another registered group bank
    # account without relying on a potentially ambiguous masked number.
    counterparty_account_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_serial: Mapped[str | None] = mapped_column(String(160), nullable=True)
    category: Mapped[str] = mapped_column(String(80), default="待确认", index=True)
    pm_project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # Canonical company cost-centre/project code (for example CC26B01).
    # Historical Feishu references remain readable and can later be
    # reconciled to pm_project_id without altering the bank-originated memo.
    project_reference: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    # unreviewed | auto_confirmed | manual_confirmed | not_internal
    internal_transfer_status: Mapped[str] = mapped_column(
        String(24), default="unreviewed", index=True
    )
    internal_transfer_source: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )
    internal_transfer_counterparty_entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_entities.id"), nullable=True, index=True
    )
    internal_transfer_reviewed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    internal_transfer_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class BankTransactionPurposeCorrection(Base):
    """Founder-reviewed correction to a bank transaction's business purpose.

    ``BankTransaction.summary`` remains the immutable bank-originated memo.
    Finance proposes a corrected business purpose here; only an approved
    correction is copied to ``BankTransaction.note``.  ``pending_key`` is set
    to the transaction id while a request is pending and cleared after review,
    providing a portable one-pending-request-per-transaction constraint in
    both PostgreSQL and the SQLite test database.
    """

    __tablename__ = "bank_transaction_purpose_corrections"
    __table_args__ = (
        UniqueConstraint(
            "pending_key",
            name="uq_bank_transaction_purpose_correction_pending",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("bank_transactions.id"), index=True
    )
    entity_id: Mapped[str] = mapped_column(ForeignKey("business_entities.id"), index=True)
    pending_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    previous_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_purpose: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class CashEntry(Base):
    __tablename__ = "cash_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("business_entities.id"), index=True)
    cash_account: Mapped[str] = mapped_column(String(120), default="公司现金")
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    category: Mapped[str] = mapped_column(String(80), default="其他")
    note: Mapped[str] = mapped_column(Text)
    pm_project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ManagedProject(Base):
    __tablename__ = "managed_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_entities.id"), nullable=True, index=True
    )
    company_name: Mapped[str] = mapped_column(String(240))
    client: Mapped[str] = mapped_column(String(240))
    client_contact: Mapped[str] = mapped_column(
        String(240), nullable=False, default="", server_default=""
    )
    business_category: Mapped[str] = mapped_column(String(120), index=True)
    manager_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    members_json: Mapped[str] = mapped_column(Text, default="[]")
    planned_start: Mapped[date] = mapped_column(Date)
    planned_end: Mapped[date] = mapped_column(Date)
    objective: Mapped[str] = mapped_column(Text)
    proposal_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    contract_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unsigned", server_default="unsigned"
    )
    contract_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    budget_revenue: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    budget_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    budget_tax: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    process_received: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    process_spent: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    process_advanced: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    process_finance_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    current_stage: Mapped[str] = mapped_column(String(120), default="立项准备")
    initiation_round: Mapped[int] = mapped_column(Integer, default=0)
    closing_round: Mapped[int] = mapped_column(Integer, default=0)
    closing_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    closing_report_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    actual_receivable: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    actual_payable: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closing_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProjectCollaborator(Base):
    """Account-based edit access delegated by a project's manager."""

    __tablename__ = "project_collaborators"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_id", name="uq_project_collaborator_project_user"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("managed_projects.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    added_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ProjectNumberSequence(Base):
    __tablename__ = "project_number_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProjectCashflowPlan(Base):
    __tablename__ = "project_cashflow_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("managed_projects.id"), index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    counterparty: Mapped[str | None] = mapped_column(String(240), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    actual_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FinanceReceivablePayable(Base):
    """A finance-entered receivable/payable that is not tied to a project."""

    __tablename__ = "finance_receivables_payables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("business_entities.id"), index=True
    )
    direction: Mapped[str] = mapped_column(String(16), index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    actual_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0")
    )
    counterparty: Mapped[str | None] = mapped_column(String(240), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    updated_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProjectProgressUpdate(Base):
    __tablename__ = "project_progress_updates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("managed_projects.id"), index=True)
    progress_percent: Mapped[int] = mapped_column(Integer)
    current_stage: Mapped[str] = mapped_column(String(120))
    completed: Mapped[str] = mapped_column(Text)
    next_step: Mapped[str] = mapped_column(Text)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_coordination: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectReview(Base):
    __tablename__ = "project_reviews"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "stage",
            "review_round",
            "reviewer_slot",
            name="uq_project_review_slot_round",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("managed_projects.id"), index=True)
    stage: Mapped[str] = mapped_column(String(20), index=True)
    review_round: Mapped[int] = mapped_column(Integer)
    reviewer_slot: Mapped[str] = mapped_column(String(40), index=True)
    reviewer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectDeletionRequest(Base):
    __tablename__ = "project_deletion_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("managed_projects.id"), index=True)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    decided_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeCategory(Base):
    """Founder-managed, stable classification for projects and uploads."""

    __tablename__ = "knowledge_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class WritingDraft(Base):
    """A private writing snapshot owned by exactly one application user."""

    __tablename__ = "writing_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # ``latest`` is the rolling auto-save slot; ``saved`` is a user-kept snapshot.
    kind: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(200))
    instruction: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scope: Mapped[str] = mapped_column(String(24), default="all")
    time_scope: Mapped[str] = mapped_column(String(24), default="all")
    generation_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    generation_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class SessionToken(Base):
    __tablename__ = "session_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(300), index=True)
    client: Mapped[str | None] = mapped_column(String(200), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    domain: Mapped[str] = mapped_column(String(40), default="training", index=True)
    status: Mapped[str] = mapped_column(String(40), default="unknown")
    confidentiality: Mapped[str] = mapped_column(String(2), default="L3")
    knowledge_status: Mapped[str] = mapped_column(String(24), default="candidate")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    documents: Mapped[list["Document"]] = relationship(back_populates="project")


class ProjectKnowledgeCard(Base):
    """A reviewable, source-grounded summary of one project."""

    __tablename__ = "project_knowledge_cards"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_project_knowledge_card"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id"),
        index=True,
    )
    sections_json: Mapped[str] = mapped_column(Text, default="{}")
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    confidentiality: Mapped[str] = mapped_column(String(2), default="L1")
    status: Mapped[str] = mapped_column(
        String(24),
        default="draft",
        index=True,
    )
    generation_mode: Mapped[str] = mapped_column(
        String(40),
        default="local_extractive",
    )
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    confirmed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    confirmation_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class FileBlob(Base):
    __tablename__ = "file_blobs"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    source_path: Mapped[str] = mapped_column(Text)
    # For files discovered directly on fnOS/SMB, retain the NAS filesystem
    # owner so review screens can identify the real uploader instead of the
    # ambiguous label "NAS直接上传". Web uploads are still attributed from the
    # immutable AuditLog entry because the container owns their staged file.
    source_owner_name: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    source_owner_uid: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    documents: Mapped[list["Document"]] = relationship(back_populates="file_blob")


class SourceHealth(Base):
    """Latest integrity observation for a content-addressed source file."""

    __tablename__ = "source_health"

    content_hash: Mapped[str] = mapped_column(
        ForeignKey("file_blobs.content_hash"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        default="unverified",
        index=True,
    )
    observed_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    observed_mtime_ns: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    observed_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    content_hash: Mapped[str] = mapped_column(ForeignKey("file_blobs.content_hash"), index=True)
    title: Mapped[str] = mapped_column(String(400), index=True)
    role: Mapped[str] = mapped_column(String(40), default="proposal")
    version: Mapped[str] = mapped_column(String(80), default="未确认")
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    knowledge_status: Mapped[str] = mapped_column(String(24), default="candidate", index=True)
    confidentiality: Mapped[str] = mapped_column(String(2), default="L3", index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    citation_basis: Mapped[str] = mapped_column(String(40), default="source-page")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="documents")
    file_blob: Mapped[FileBlob] = relationship(back_populates="documents")
    contract_source: Mapped["ContractDocumentSource | None"] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        uselist=False,
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[list["DocumentArtifact"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class ContractDocumentOwner(Base):
    """Records every employee who uploaded a contract document.

    A document may have more than one uploader when an identical source file
    is submitted twice.  The association therefore cannot live directly on
    ``Document`` and must remain independent from the NAS folder layout.
    """

    __tablename__ = "contract_document_owners"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "uploaded_by_user_id",
            name="uq_contract_document_uploader",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    uploaded_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ContractDocumentSource(Base):
    """Physical NAS copy assigned to one contract security context.

    ``FileBlob`` remains content-addressed and can therefore be shared by
    documents with identical bytes.  Contract copies still need an independent
    location because the same bytes may legitimately exist in separate L4/L5
    archives and must be movable without touching the other security context.
    """

    __tablename__ = "contract_document_sources"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id"), primary_key=True
    )
    source_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    document: Mapped[Document] = relationship(back_populates="contract_source")


class ReviewProposal(Base):
    """A staged metadata change that never publishes knowledge by itself."""

    __tablename__ = "review_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id"),
        index=True,
    )
    project_name: Mapped[str] = mapped_column(String(300))
    client: Mapped[str | None] = mapped_column(String(200), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    domain: Mapped[str] = mapped_column(String(40))
    document_role: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(80))
    confidentiality: Mapped[str] = mapped_column(String(2))
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending_founder",
        index=True,
    )
    submitted_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    decided_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class InboxIssue(Base):
    """An unresolved NAS inbox item that needs administrator attention."""

    __tablename__ = "inbox_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    relative_path: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    error_code: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(String(300))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    modified_ns: Mapped[int] = mapped_column(BigInteger, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    page: Mapped[int] = mapped_column(Integer, default=1)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    section: Mapped[str | None] = mapped_column(String(300), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    document: Mapped[Document] = relationship(back_populates="chunks")
    embeddings: Mapped[list["ChunkEmbedding"]] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
    )


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "model_name", name="uq_chunk_embedding_model"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"), index=True)
    model_name: Mapped[str] = mapped_column(String(160), index=True)
    dimensions: Mapped[int] = mapped_column(Integer)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list[float]] = mapped_column(PortableVector())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    chunk: Mapped[Chunk] = relationship(back_populates="embeddings")


class MaintainedArtifact(Base):
    """A governed baseline such as the current company introduction."""

    __tablename__ = "maintained_artifacts"
    __table_args__ = (
        UniqueConstraint("name", name="uq_maintained_artifact_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(240), index=True)
    artifact_type: Mapped[str] = mapped_column(String(40), index=True)
    current_document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id"),
        index=True,
    )
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    audience: Mapped[str] = mapped_column(String(16), default="external")
    confidentiality: Mapped[str] = mapped_column(String(2), default="L1")
    cutoff_date: Mapped[date] = mapped_column(Date)
    review_cadence_days: Mapped[int] = mapped_column(Integer, default=90)
    next_review_at: Mapped[date] = mapped_column(Date, index=True)
    last_reviewed_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    section_map_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(
        String(24),
        default="active",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class EvolutionReviewRun(Base):
    """One immutable review window for a maintained artifact."""

    __tablename__ = "evolution_review_runs"
    __table_args__ = (
        UniqueConstraint(
            "artifact_id",
            "reviewed_through",
            name="uq_evolution_artifact_review_date",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("maintained_artifacts.id"),
        index=True,
    )
    cutoff_date: Mapped[date] = mapped_column(Date)
    reviewed_through: Mapped[date] = mapped_column(Date, index=True)
    confidentiality: Mapped[str] = mapped_column(String(2), default="L1")
    status: Mapped[str] = mapped_column(
        String(24),
        default="open",
        index=True,
    )
    generation_mode: Mapped[str] = mapped_column(
        String(40),
        default="local_deterministic",
    )
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )


class EvolutionCandidateRecord(Base):
    """A persisted candidate whose evidence still resolves to a source."""

    __tablename__ = "evolution_candidate_records"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "candidate_key",
            name="uq_evolution_run_candidate_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("evolution_review_runs.id"),
        index=True,
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("maintained_artifacts.id"),
        index=True,
    )
    candidate_key: Mapped[str] = mapped_column(String(180))
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id"),
        index=True,
    )
    source_content_hash: Mapped[str] = mapped_column(String(64), index=True)
    target_section: Mapped[str] = mapped_column(String(80))
    suggested_action: Mapped[str] = mapped_column(String(40))
    classification: Mapped[str] = mapped_column(String(24), index=True)
    score_band: Mapped[str] = mapped_column(String(24))
    score: Mapped[int] = mapped_column(Integer)
    disclosure_status: Mapped[str] = mapped_column(
        String(40),
        index=True,
    )
    review_status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        index=True,
    )
    payload_json: Mapped[str] = mapped_column(Text)
    decided_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )


class EvolutionChangePlan(Base):
    """A reviewable plan; never a published company artifact."""

    __tablename__ = "evolution_change_plans"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_evolution_change_plan_run"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("evolution_review_runs.id"),
        index=True,
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("maintained_artifacts.id"),
        index=True,
    )
    plan_json: Mapped[str] = mapped_column(Text)
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    query_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    denied_count: Mapped[int] = mapped_column(Integer, default=0)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EducationCohort(Base):
    __tablename__ = "education_cohorts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("business_entities.id"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date)
    course_period: Mapped[str] = mapped_column(String(20), default="1_month", server_default="1_month")
    student_count: Mapped[int] = mapped_column(Integer, default=0)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EducationCashEntry(Base):
    __tablename__ = "education_cash_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("education_cohorts.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    direction: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    occurred_on: Mapped[date] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    purpose: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(40), default="其他", server_default="其他")
    detail: Mapped[str] = mapped_column(String(80), default="其他", server_default="其他")
    staff_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EducationStaff(Base):
    __tablename__ = "education_staff"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("education_cohorts.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EducationStudent(Base):
    __tablename__ = "education_students"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("education_cohorts.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    student_no: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    registration_date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(80))
    gender: Mapped[str] = mapped_column(String(10))
    age: Mapped[int] = mapped_column(Integer)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    identity_number: Mapped[str] = mapped_column(String(32), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    guardian_name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    guardian_phone: Mapped[str] = mapped_column(String(30), default="", server_default="")
    emergency_contact: Mapped[str] = mapped_column(String(240), default="", server_default="")
    health_notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    referrer_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    referral_channel: Mapped[str] = mapped_column(String(160), default="", server_default="")
    game: Mapped[str] = mapped_column(String(40))
    game_account: Mapped[str] = mapped_column(String(100), default="", server_default="")
    current_rank: Mapped[str] = mapped_column(String(100), default="", server_default="")
    course_period: Mapped[str] = mapped_column(String(20))
    study_start: Mapped[date] = mapped_column(Date)
    study_end: Mapped[date] = mapped_column(Date)
    accommodation_days: Mapped[int] = mapped_column(Integer, default=0)
    room_type: Mapped[str] = mapped_column(String(10))
    fee_notes: Mapped[str] = mapped_column(Text, default="")
    fees_json: Mapped[str] = mapped_column(Text, default="[]")
    staff_assignments_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    receivable: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    received: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    learning_status: Mapped[str] = mapped_column(String(24), default="已报名", server_default="已报名", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EducationAssessment(Base):
    __tablename__ = "education_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("education_students.id"), index=True)
    evaluator_staff_id: Mapped[str] = mapped_column(ForeignKey("education_staff.id"))
    stage: Mapped[str] = mapped_column(String(20))
    assessed_on: Mapped[date] = mapped_column(Date)
    content_json: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EducationInstallment(Base):
    """A planned package payment; it is not cash until linked receipts exist."""

    __tablename__ = "education_installments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("education_students.id"), index=True)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("education_cohorts.id"), index=True)
    label: Mapped[str] = mapped_column(String(80))
    due_on: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    note: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EducationPayment(Base):
    """Auditable receipt/refund detail that maintains the student's net received total."""

    __tablename__ = "education_payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(ForeignKey("education_students.id"), index=True)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("education_cohorts.id"), index=True)
    installment_id: Mapped[str | None] = mapped_column(ForeignKey("education_installments.id"), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    method: Mapped[str] = mapped_column(String(24), default="银行转账")
    account: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EducationCostDocument(Base):
    """One dated cost item whose total is derived from its daily unit price."""

    __tablename__ = "education_cost_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("business_entities.id"), index=True)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[str] = mapped_column(String(80), default="其他")
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0"
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    vendor: Mapped[str] = mapped_column(String(240), default="")
    document_no: Mapped[str] = mapped_column(String(120), default="")
    source_ref: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EducationCostAttachment(Base):
    """A private NAS-backed voucher or attachment for a source cost document."""

    __tablename__ = "education_cost_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cost_document_id: Mapped[str] = mapped_column(ForeignKey("education_cost_documents.id"), index=True)
    filename: Mapped[str] = mapped_column(String(180))
    source_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EducationCostAllocation(Base):
    """Analytical ownership of a source cost by cohort/month and optionally student."""

    __tablename__ = "education_cost_allocations"
    __table_args__ = (
        UniqueConstraint("cost_document_id", "cohort_id", "student_id", "allocation_month", name="uq_education_cost_allocation_target"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cost_document_id: Mapped[str] = mapped_column(ForeignKey("education_cost_documents.id"), index=True)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("education_cohorts.id"), index=True)
    student_id: Mapped[str | None] = mapped_column(ForeignKey("education_students.id"), nullable=True, index=True)
    allocation_month: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    note: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EducationScheduleDay(Base):
    __tablename__ = "education_schedule_days"
    __table_args__ = (
        UniqueConstraint("cohort_id", "calendar_date", name="uq_education_schedule_day"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("education_cohorts.id"), index=True)
    calendar_date: Mapped[date] = mapped_column(Date, index=True)
    day_number: Mapped[int] = mapped_column(Integer)
    day_type: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    report_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    updated_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EducationMonthlySummary(Base):
    __tablename__ = "education_monthly_summaries"
    __table_args__ = (
        UniqueConstraint("cohort_id", "month", name="uq_education_monthly_summary"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("education_cohorts.id"), index=True)
    month: Mapped[date] = mapped_column(Date, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    achievements: Mapped[str] = mapped_column(Text, default="")
    problems: Mapped[str] = mapped_column(Text, default="")
    next_month_plan: Mapped[str] = mapped_column(Text, default="")
    updated_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EducationDailyLog(Base):
    __tablename__ = "education_daily_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cohort_id: Mapped[str] = mapped_column(ForeignKey("education_cohorts.id"), index=True)
    schedule_day_id: Mapped[str | None] = mapped_column(ForeignKey("education_schedule_days.id"), nullable=True, index=True)
    log_date: Mapped[date] = mapped_column(Date, index=True)
    staff_id: Mapped[str] = mapped_column(ForeignKey("education_staff.id"), index=True)
    log_type: Mapped[str] = mapped_column(String(24), index=True)
    summary: Mapped[str] = mapped_column(Text)
    student_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    follow_up: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DocumentArtifact(Base):
    __tablename__ = "document_artifacts"
    __table_args__ = (
        UniqueConstraint("document_id", "kind", name="uq_document_artifact_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="ready")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    document: Mapped[Document] = relationship(back_populates="artifacts")
