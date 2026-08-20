from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    scope: str = Field(default="auto", pattern="^(auto|current|history|all)$")
    retrieval: str = Field(
        default="auto",
        pattern="^(auto|exact|semantic|hybrid)$",
    )
    limit: int = Field(default=8, ge=1, le=20)
    category: str | None = Field(default=None, min_length=1, max_length=40)


class ContractSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    category: Literal[
        "administrative",
        "personnel",
        "business",
        "executive_office",
    ]
    limit: int = Field(default=20, ge=1, le=50)


class ContractFolderCreateRequest(BaseModel):
    category: Literal[
        "administrative",
        "personnel",
        "business",
        "executive_office",
    ]
    folder_path: str = Field(min_length=1, max_length=400)


class ContractFolderMoveRequest(BaseModel):
    folder_path: str = Field(default="", max_length=400)


class WritingDraftRequest(BaseModel):
    instruction: str = Field(min_length=5, max_length=3000)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    scope: str = Field(default="all", pattern="^(current|history|all)$")
    allow_l3_generation: bool = False


class WritingDraftSaveRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    instruction: str = Field(min_length=5, max_length=3000)
    draft: str = Field(min_length=1, max_length=200000)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    scope: str = Field(default="all", pattern="^(current|history|all)$")
    time_scope: str | None = Field(
        default=None,
        pattern="^(current|history|all)$",
    )
    generation_mode: str | None = Field(default=None, max_length=40)
    generation_model: str | None = Field(default=None, max_length=160)
    sources: list[dict[str, object]] = Field(default_factory=list, max_length=100)
    response: dict[str, object] | None = None


class KnowledgeCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class KnowledgeCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class ProposalBrief(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    objective: str | None = Field(default=None, max_length=1000)
    audience: str | None = Field(default=None, max_length=400)
    budget: str | None = Field(default=None, max_length=200)
    geography: str | None = Field(default=None, max_length=200)
    duration: str | None = Field(default=None, max_length=200)
    deliverables: str | None = Field(default=None, max_length=1000)


LocalRole = Literal[
    "administrative",
    "personnel",
    "business",
    "finance",
    "management",
]
ConfidentialityLevel = Literal["L1", "L2", "L3", "L4", "L5"]
class AdminUserCreate(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=80,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    role: LocalRole = "business"
    confidentiality_ceiling: ConfidentialityLevel = "L1"
    departments: list[str] = Field(
        default_factory=lambda: ["*"],
        max_length=50,
    )


class AdminUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: LocalRole | None = None
    confidentiality_ceiling: ConfidentialityLevel | None = None
    departments: list[str] | None = Field(
        default=None,
        max_length=50,
    )
    active: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=200)


class OwnPasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


DocumentRole = Literal[
    "company_profile",
    "proposal",
    "execution",
    "brief",
    "closing_report",
    "asset",
    "contract",
]


class ReviewProposalRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=300)
    client: str | None = Field(default=None, max_length=200)
    year: int | None = Field(default=None, ge=2000, le=2100)
    domain: str = Field(min_length=1, max_length=40)
    document_role: DocumentRole
    version: str = Field(min_length=1, max_length=80)
    confidentiality: ConfidentialityLevel
    is_final: bool = False
    note: str | None = Field(default=None, max_length=1000)


class ReviewApplyRequest(BaseModel):
    proposal_id: str = Field(min_length=36, max_length=36)
    confirmation: Literal["确认应用"]


class ReviewRejectRequest(BaseModel):
    proposal_id: str = Field(min_length=36, max_length=36)
    confirmation: Literal["确认退回"]
    reason: str | None = Field(default=None, max_length=500)


class BatchReviewConfirmRequest(BaseModel):
    # The Web client normally submits 50 at a time, but the API also accepts
    # one-click batches from an already-open (older) page.  Keep a generous
    # server-side ceiling so a stale client cannot turn a successful review
    # into a validation error after the data has already been confirmed.
    document_ids: list[str] = Field(min_length=1, max_length=500)


class ReviewIngestionRejectRequest(BaseModel):
    confirmation: Literal["确认拒绝入库"]
    reason: str | None = Field(default=None, max_length=500)


class BatchReviewRejectRequest(ReviewIngestionRejectRequest):
    document_ids: list[str] = Field(min_length=1, max_length=500)


class GovernanceConfidentialityUpdateRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=500)
    confidentiality: ConfidentialityLevel
    reason: str = Field(min_length=4, max_length=500)
    confirmation: Literal["确认调整资料密级"]


class GovernanceAIClassifyRequest(BaseModel):
    dry_run: bool = True
    confirmation: Literal["确认AI梳理资料密级"]


class PublicationRequest(BaseModel):
    confirmation: Literal["确认发布为当前版本"]
    supersedes_document_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    note: str | None = Field(default=None, max_length=500)


class BusinessGoldImportRequest(BaseModel):
    cases: list[dict] = Field(min_length=1, max_length=200)
    confirmation: Literal["确认导入业务金标草稿"]


class BusinessGoldApprovalRequest(BaseModel):
    case_ids: list[str] = Field(min_length=1, max_length=200)
    confirmation: Literal["确认批准业务金标"]
    owner_note: str = Field(min_length=4, max_length=500)


class BusinessGoldGenerateRequest(BaseModel):
    target: int = Field(default=150, ge=1, le=150)
    confirmation: Literal["确认生成业务金标候选题"]


class EvolutionDigestRequest(BaseModel):
    artifact: Literal[
        "company_profile",
        "capability_deck",
        "case_library",
        "team_profile",
    ] = "company_profile"
    cutoff_date: date
    reviewed_through: date
    audience: Literal["internal", "external"] = "external"
    limit: int = Field(default=30, ge=1, le=100)


class MaintainedArtifactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    artifact_type: Literal[
        "company_profile",
        "capability_deck",
        "case_library",
        "team_profile",
    ] = "company_profile"
    current_document_id: str = Field(min_length=36, max_length=36)
    audience: Literal["internal", "external"] = "external"
    cutoff_date: date | None = None
    review_cadence_days: int = Field(default=90, ge=30, le=365)
    section_map: dict[str, str] = Field(default_factory=dict)


class MaintainedArtifactBaselineUpdate(BaseModel):
    current_document_id: str = Field(min_length=36, max_length=36)
    cutoff_date: date
    confirmation: Literal["确认更新维护资料基线"]


class EvolutionArtifactRunRequest(BaseModel):
    reviewed_through: date | None = None
    limit: int = Field(default=30, ge=1, le=100)


class EvolutionCandidateDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    confirmation: str = Field(min_length=4, max_length=40)
    note: str | None = Field(default=None, max_length=500)


class EvolutionChangePlanRequest(BaseModel):
    confirmation: Literal["确认生成变更计划"]


class EvolutionReviewCloseRequest(BaseModel):
    confirmation: Literal["确认完成本次复核"]
