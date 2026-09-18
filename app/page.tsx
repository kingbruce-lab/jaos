"use client";

import { FormEvent, Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AccountRoleFields, EducationWorkspace } from "./education-workspace";

type User = {
  id: string;
  username: string;
  display_name: string;
  role: string;
  organization_role: string;
  confidentiality_ceiling: string;
  departments: string[];
};

type AdminUser = User & {
  active: boolean;
  external_identity: string | null;
  created_at: string;
};

type KnowledgeCategory = {
  id: string;
  key: string;
  name: string;
  active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

type Status = {
  status: string;
  environment: string;
  database: string;
  retrieval: {
    exact: boolean;
    semantic: boolean;
    llm_generation: boolean;
    outbound_enabled: boolean;
  };
  counts: {
    projects: number;
    documents: number | null;
    chunks: number | null;
    current_documents: number | null;
    candidate_documents: number | null;
    source_available_documents: number | null;
    source_missing_documents: number | null;
  };
  policy_version: string;
};

type OperationComponent = {
  status: string;
  message: string;
  used_percent?: number | null;
  free_gb?: number | null;
  total_gb?: number | null;
  used_gb?: number | null;
  latest_completed_at?: string | null;
  age_seconds?: number | null;
  manifest_sealed?: boolean;
  media_configured?: boolean;
  media_available?: boolean;
  separate_device?: boolean;
  verified?: boolean;
  latest_package?: string | null;
  embedding_enabled?: boolean;
  embedding_model?: string;
  llm_enabled?: boolean;
  primary_model?: string;
  fallback_model?: string;
  l3_outbound_enabled?: boolean;
  technical_status?: string;
  technical_case_count?: number;
  business_gold_total?: number;
  concurrency_status?: string;
  concurrency_p95_ms?: number | null;
  concurrency_request_count?: number;
  concurrency_error_count?: number;
  latest_scan_at?: string | null;
  open_issue_count?: number;
  unhealthy_count?: number;
  counts?: Record<string, number>;
  generated_at?: string | null;
  metrics?: {
    page_citation_accuracy?: number;
    refusal_accuracy?: number;
    permission_leak_count?: number;
    retrieval_p95_ms?: number;
  };
};

type OperationsStatus = {
  status: "ok" | "warning" | "critical";
  components: {
    database: OperationComponent;
    storage: OperationComponent;
    memory: OperationComponent;
    backup: OperationComponent;
    offsite_backup: OperationComponent;
    gateway: OperationComponent;
    evaluation: OperationComponent;
    ingestion: OperationComponent;
    source_integrity: OperationComponent;
  };
  recommendations: string[];
  thresholds: {
    disk_warning_percent: number;
    disk_critical_percent: number;
    memory_warning_percent: number;
    memory_critical_percent: number;
    backup_max_age_seconds: number;
    offsite_backup_max_age_seconds: number;
  };
  generated_at: string;
};

type BusinessGoldCase = {
  id: string;
  category: string;
  question: string;
  scope: "auto" | "current" | "history" | "all";
  retrieval: "auto" | "exact" | "semantic" | "hybrid";
  limit: number;
  actor: {
    role: string;
    confidentiality_ceiling: string;
  };
  expected: {
    document_id?: string;
    page?: number;
    reference_answer?: string;
    key_points?: string[];
    forbidden_claims?: string[];
    expect_refusal?: boolean;
    expect_no_leak?: boolean;
  };
  approved: boolean;
  owner_note?: string;
};

type BusinessGoldRegistry = {
  target: number;
  total: number;
  approved: number;
  pending: number;
  invalid: number;
  quality_ready: number;
  errors: { line: number; reason: string }[];
  cases: BusinessGoldCase[];
  generation?: {
    requested: number;
    created: number;
    shortfall: number;
    counts: Record<string, number>;
  };
};

type BusinessGoldSource = {
  document_id: string;
  title: string;
  version: string;
  page_count: number;
  knowledge_status: string;
  confidentiality: string;
  project_id: string;
  project: string;
};

type Project = {
  id: string;
  name: string;
  client: string | null;
  year: number | null;
  domain: string;
  status: string;
  knowledge_status: string;
  confirmed: boolean;
  document_count: number;
  has_closing_report: boolean;
  closing_report_reminder: boolean;
};

type MoneyValue = number | string | null;

type FinanceRankItem = {
  name: string;
  amount: MoneyValue;
  transaction_count: number;
};

type FinanceHealthSnapshot = {
  data_as_of: string | null;
  freshness_days: number | null;
  freshness_status?: "fresh" | "attention" | "stale" | "no_data";
  minimum_balance: {
    amount: MoneyValue | null;
    date: string | null;
    account_count: number;
    covered_account_count: number;
    coverage_start?: string | null;
    covered_days?: number;
    total_days?: number;
    coverage_complete?: boolean;
  };
  maximum_daily_net_outflow: {
    amount: MoneyValue | null;
    date: string | null;
    net: MoneyValue | null;
  };
  average_weekly_net_inflow_4w: {
    amount: MoneyValue | null;
    period_start: string | null;
    period_end: string | null;
    weeks: unknown[];
  };
  top3_income_concentration: {
    amount: MoneyValue;
    total: MoneyValue;
    ratio: number | string | null;
    parties: FinanceRankItem[];
  };
  top3_expense_concentration: {
    amount: MoneyValue;
    total: MoneyValue;
    ratio: number | string | null;
    parties: FinanceRankItem[];
  };
  unclassified: {
    amount: MoneyValue;
    count: number;
    income: MoneyValue;
    expense: MoneyValue;
  };
  internal_transfers: {
    gross_amount: MoneyValue;
    count: number;
    income: MoneyValue;
    expense: MoneyValue;
    auto_count: number;
    manual_count: number;
  };
  scope?: "excluding_internal_transfers" | "including_internal_transfers" | string;
};

type FinanceInternalTransfer = {
  id: string;
  transaction_id?: string;
  matched_transaction_id?: string | null;
  transaction_date: string;
  transacted_at?: string;
  source_entity_id?: string | null;
  source_entity_name: string;
  company?: string;
  target_entity_id?: string | null;
  target_entity_name: string;
  counterparty?: string | null;
  summary?: string | null;
  amount: MoneyValue;
  confidence?: number | string | null;
  reason?: string | null;
  status: "candidate" | "confirmed" | "rejected" | string;
  review_status?: "candidate" | "confirmed" | "rejected" | "unreviewed" | string;
  decision_status?: "candidate" | "confirmed" | "rejected" | "unreviewed" | string;
  candidate_reason?: string | null;
};

type FinanceInternalTransferRegistry = {
  confirmed_amount: MoneyValue;
  candidate_amount: MoneyValue;
  confirmed_count: number;
  candidate_count: number;
  items: FinanceInternalTransfer[];
};

type FinanceInternalTransferApiRegistry = {
  items?: (FinanceInternalTransfer & { decision_status?: string })[];
  summary?: {
    candidate_count?: number;
    confirmed_count?: number;
    rejected_count?: number;
    gross_amount?: MoneyValue;
  };
  candidate_count?: number;
  confirmed_count?: number;
  rejected_count?: number;
  candidate_amount?: MoneyValue;
  confirmed_amount?: MoneyValue;
};

function normalizeFinanceTransferRegistry(payload: FinanceInternalTransferApiRegistry | null | undefined): FinanceInternalTransferRegistry {
  const items = (payload?.items || []).map((item) => ({
    ...item,
    transaction_id: item.transaction_id || item.id,
    status: item.decision_status || item.review_status || item.status,
    transaction_date: item.transaction_date || item.transacted_at || "",
    source_entity_name: item.source_entity_name || item.company || "",
    target_entity_name: item.target_entity_name || "",
    reason: item.reason || item.candidate_reason || null,
  }));
  const candidates = items.filter((item) => item.status === "candidate");
  const confirmed = items.filter((item) => item.status === "confirmed");
  return {
    items,
    candidate_count: payload?.candidate_count ?? payload?.summary?.candidate_count ?? candidates.length,
    confirmed_count: payload?.confirmed_count ?? payload?.summary?.confirmed_count ?? confirmed.length,
    candidate_amount: payload?.candidate_amount ?? candidates.reduce((total, item) => total + Number(item.amount || 0), 0),
    confirmed_amount: payload?.confirmed_amount ?? payload?.summary?.gross_amount
      ?? confirmed.reduce((total, item) => total + Number(item.amount || 0), 0),
  };
}

type FinanceAlertItem = {
  id: string;
  batch_id: string;
  transaction_date: string;
  counterparty: string;
  summary: string;
  income: MoneyValue;
  expense: MoneyValue;
  amount: MoneyValue;
  status: string;
  severity: "high" | "medium" | "low";
  reasons: string[];
  alert_type?: string | null;
  rule_code?: string | null;
  rule_codes?: string[];
};

type FinanceDashboard = {
  confidentiality: "L4";
  period_start: string;
  period_end: string;
  income: MoneyValue;
  expense: MoneyValue;
  net: MoneyValue;
  weekly_top_income: FinanceRankItem[];
  weekly_top_expense: FinanceRankItem[];
  anomaly_count: number;
  anomalies: FinanceAlertItem[];
  monthly_top_income: FinanceRankItem[];
  monthly_top_expense: FinanceRankItem[];
  monthly_anomaly_count: number;
  monthly_anomalies: FinanceAlertItem[];
  previous_month: {
    period_start: string;
    period_end: string;
    income: MoneyValue;
    expense: MoneyValue;
    net: MoneyValue;
  };
  current_year: {
    period_start: string;
    period_end: string;
    income: MoneyValue;
    expense: MoneyValue;
    net: MoneyValue;
  };
  bank_balance: MoneyValue;
  cash_balance: MoneyValue;
  total_balance: MoneyValue;
  pending_batches: boolean;
  accounts: {
    company: string;
    bank_name: string;
    account: string;
    balance: MoneyValue;
    as_of: string;
  }[];
  weekly: {
    year: number;
    week: number;
    week_start: string;
    income: MoneyValue;
    expense: MoneyValue;
    net: MoneyValue;
  }[];
  fund_health?: FinanceHealthSnapshot;
  health?: FinanceHealthSnapshot;
  include_internal_transfers?: boolean;
  internal_transfer_summary?: Omit<FinanceInternalTransferRegistry, "items">;
  receivables_payables?: {
    receivable: FinanceReceivablePayableSummary;
    payable: FinanceReceivablePayableSummary;
  };
};

type FinanceReceivablePayableItem = {
  id: string;
  source: "project" | "finance" | "education";
  entity_id: string;
  project_id: string | null;
  project_no: string | null;
  project_name: string | null;
  direction: "receivable" | "payable";
  due_date: string;
  amount: MoneyValue;
  actual_amount: MoneyValue;
  outstanding_amount: MoneyValue;
  counterparty: string | null;
  note: string | null;
  overdue: boolean;
};

type FinanceReceivablePayableSummary = {
  total: MoneyValue;
  count: number;
  items: FinanceReceivablePayableItem[];
};

type FinanceAnnualYears = {
  entity_id: string;
  years: number[];
  default_view: "realtime";
  current_year: number;
};

type FinanceAnnualDashboard = {
  confidentiality: "L4";
  entity_id: string;
  entity_name: string;
  year: number;
  period_start: string;
  period_end: string;
  confirmed_only: boolean;
  include_internal_transfers: boolean;
  coverage: {
    data_complete: boolean;
    confirmed_period_start: string | null;
    confirmed_period_end: string | null;
    confirmed_batch_count: number;
    pending_batch_count: number;
    pending_batches: { id: string; filename: string; period_start: string | null; period_end: string | null; status: string }[];
  };
  income: MoneyValue;
  expense: MoneyValue;
  net: MoneyValue;
  opening_balance: MoneyValue;
  closing_balance: MoneyValue;
  balance_change: MoneyValue;
  transaction_count: number;
  income_transaction_count: number;
  expense_transaction_count: number;
  average_income: MoneyValue;
  average_expense: MoneyValue;
  largest_income: MoneyValue;
  largest_expense: MoneyValue;
  counterparty_count: number;
  monthly: { month: number; income: MoneyValue; expense: MoneyValue; net: MoneyValue; transaction_count: number }[];
  top_income: FinanceRankItem[];
  top_expense: FinanceRankItem[];
  income_concentration: { amount: MoneyValue; total: MoneyValue; ratio: MoneyValue; parties: FinanceRankItem[] };
  expense_concentration: { amount: MoneyValue; total: MoneyValue; ratio: MoneyValue; parties: FinanceRankItem[] };
  income_categories: { name: string; amount: MoneyValue; transaction_count: number; ratio: MoneyValue }[];
  expense_categories: { name: string; amount: MoneyValue; transaction_count: number; ratio: MoneyValue }[];
  largest_outflow_days: { date: string; income: MoneyValue; expense: MoneyValue; net: MoneyValue; transaction_count: number }[];
  anomaly_count: number;
  anomalies: FinanceAlertItem[];
  unclassified: { count: number; amount: MoneyValue; ratio: MoneyValue };
  internal_transfers: { count: number; income: MoneyValue; expense: MoneyValue };
};

type FinanceEntity = {
  id: string;
  key: "jingao" | "ace-leopard" | "power-leopard" | "xingyao";
  name: string;
  display_name: string;
  business_name: string;
  account_label: string;
  default_bank_name: string;
  is_headquarters: boolean;
  show_cash: boolean;
};

type FinanceBatch = {
  id: string;
  entity_id: string;
  company: string;
  bank_name: string;
  account: string;
  filename: string;
  period_start: string;
  period_end: string;
  status: string;
  row_count: number;
  duplicate_count: number;
  error_count: number;
  uploader: string;
  confirmer: string;
  confirmed_at: string | null;
  created_at: string;
};

type FinanceTransaction = {
  id: string;
  transacted_at: string;
  income: MoneyValue;
  expense: MoneyValue;
  balance: MoneyValue;
  counterparty: string | null;
  summary: string | null;
  category: string;
  note: string | null;
  pm_project_id: string | null;
  project_reference: string | null;
  project_reference_label?: string | null;
  project_reference_valid?: boolean;
  status: string;
  purpose_correction: FinancePurposeCorrection | null;
};

type FinanceAnnualTransactionSearch = {
  confidentiality: "L4";
  entity_id: string;
  entity_name: string;
  year: number;
  query: string;
  confirmed_only: boolean;
  include_internal_transfers: boolean;
  total: number;
  limit: number;
  items: FinanceAnnualTransactionSearchItem[];
};

type FinanceAnnualTransactionSearchItem = {
  id: string;
  batch_id: string;
  batch_filename: string;
  transacted_at: string;
  income: MoneyValue;
  expense: MoneyValue;
  balance: MoneyValue | null;
  counterparty: string | null;
  summary: string | null;
  note: string | null;
  category: string;
  project_reference: string | null;
  bank_serial: string | null;
  bank_name: string;
  account: string;
  matched_fields: string[];
};

type FinanceCostCenterSummary = {
  code: string;
  label: string;
  group: string;
  income: MoneyValue;
  expense: MoneyValue;
  net: MoneyValue;
  transaction_count: number;
};

type FinanceCostCenterRegistry = {
  confidentiality: "L4";
  entity_id: string;
  entity_name: string;
  confirmed_only: boolean;
  include_internal_transfers: boolean;
  items: FinanceCostCenterSummary[];
};

type FinanceCostCenterLedger = {
  confidentiality: "L4";
  entity_id: string;
  entity_name: string;
  code: string;
  label: string;
  confirmed_only: boolean;
  include_internal_transfers: boolean;
  income: MoneyValue;
  expense: MoneyValue;
  net: MoneyValue;
  transaction_count: number;
  items: Omit<FinanceAnnualTransactionSearchItem, "matched_fields">[];
};

type FinancePurposeCorrection = {
  id: string;
  transaction_id: string;
  entity_id: string;
  previous_purpose: string | null;
  proposed_purpose: string;
  status: "pending" | "approved" | "rejected";
  requested_by: string;
  requested_at: string;
  reviewed_by: string;
  reviewed_at: string | null;
  review_comment: string | null;
  transaction: {
    transacted_at: string | null;
    counterparty: string | null;
    income: MoneyValue;
    expense: MoneyValue;
    summary: string | null;
    current_purpose: string | null;
    batch_id: string | null;
    batch_filename: string;
  };
};

type FinancePurposeCorrectionRegistry = {
  items: FinancePurposeCorrection[];
  pending_count: number;
  approved_count: number;
  rejected_count: number;
};

type CashLedgerEntry = {
  id: string;
  company: string;
  cash_account: string;
  transaction_date: string;
  direction: "opening" | "income" | "expense";
  amount: MoneyValue;
  category: string;
  note: string;
  pm_project_id: string | null;
};

type ProjectReviewSlot = {
  slot: "founder";
  label: string;
  decision: "pending" | "approved" | "rejected";
  note: string | null;
  reviewer: string | null;
  decided_at: string | null;
};

type ProjectCashflow = {
  id: string;
  direction: "receivable" | "payable";
  due_date: string;
  amount: MoneyValue;
  counterparty: string | null;
  note: string | null;
  actual_amount: MoneyValue;
  actual_date: string | null;
  running_cash: MoneyValue;
};

type ProjectCollaboratorAccount = {
  user_id: string;
  username: string;
  display_name: string;
  active?: boolean;
  added_at?: string;
};

type ManagedProject = {
  id: string;
  project_no: string;
  name: string;
  company_name: string;
  client: string;
  client_contact: string | null;
  business_category: string;
  manager: string;
  manager_user_id: string;
  members: string[];
  collaborators: ProjectCollaboratorAccount[];
  planned_start: string;
  planned_end: string;
  objective: string;
  contract_document_id: string | null;
  contract_status?: "unsigned" | "signed_received";
  contract_alert?: boolean;
  contract_unsigned_alert?: boolean;
  contract_alert_message?: string | null;
  contract_amount: MoneyValue;
  budget_revenue: MoneyValue;
  budget_cost: MoneyValue;
  budget_tax: MoneyValue;
  expected_margin: MoneyValue;
  process_received: MoneyValue;
  process_spent: MoneyValue;
  process_advanced: MoneyValue;
  process_finance_updated_at: string | null;
  bank_received: MoneyValue;
  bank_spent: MoneyValue;
  bank_transaction_count: number;
  status: string;
  progress_percent: number;
  current_stage: string;
  proposal_attached: boolean;
  closing_report_attached: boolean;
  created_at: string;
  updated_at: string;
  cashflow_plans?: ProjectCashflow[];
  maximum_funding_gap?: MoneyValue;
  progress_updates?: {
    id: string;
    progress_percent: number;
    current_stage: string;
    completed: string;
    next_step: string;
    risks: string | null;
    needs_coordination: boolean;
    creator: string;
    created_at: string;
  }[];
  initiation_reviews?: ProjectReviewSlot[];
  closing_reviews?: ProjectReviewSlot[];
  closing_summary?: string | null;
  actual_revenue?: MoneyValue;
  actual_cost?: MoneyValue;
  actual_receivable?: MoneyValue;
  actual_payable?: MoneyValue;
  planned_receivable: MoneyValue;
  received_amount: MoneyValue;
  outstanding_receivable: MoneyValue;
  payment_complete: boolean;
  portfolio_group: "ongoing" | "closed_unpaid" | "pipeline" | "ready_archive" | "archived";
  deletion_request?: {
    id: string;
    status: "pending" | "approved" | "rejected";
    reason: string;
    requester: string;
    decision_note: string | null;
    decider: string | null;
    created_at: string;
    decided_at: string | null;
  } | null;
};

type ManagedProjectRegistry = {
  counts: Record<string, number>;
  portfolio_counts: Record<string, number>;
  items: ManagedProject[];
};

type ProjectCollaboratorRegistry = {
  items: ProjectCollaboratorAccount[];
};

type FounderDeletePasswordStatus = {
  configured: boolean;
  minimum_length: number;
  status?: "configured" | "updated";
};

type SearchResult = {
  document_id: string;
  title: string;
  version: string;
  page: number;
  citation_basis: string;
  project_id: string;
  project: string;
  domain: string;
  knowledge_status: string;
  confidentiality: string;
  excerpt: string;
  score: number;
  matched_pages?: number[];
};

type SearchResponse = {
  query_id: string | null;
  retrieval_mode: string;
  retrieval_degraded: boolean;
  scope: string;
  scope_reason: string;
  answer: string;
  generation_mode: "llm" | "deterministic" | "local_only";
  generation_model: string | null;
  generation_fallback_used: boolean;
  generation_degraded: boolean;
  results: SearchResult[];
  total: number;
  offset: number;
  limit: number;
  denied_count: number;
  unavailable_count: number;
};

type ReviewProposalItem = {
  id: string;
  document_id: string;
  project_name: string;
  client: string | null;
  year: number | null;
  domain: string;
  document_role: string;
  version: string;
  confidentiality: string;
  is_final: boolean;
  note: string | null;
  decision_note: string | null;
  status: string;
  submitted_by: string;
  decided_by: string | null;
  created_at: string;
  decided_at: string | null;
};

type PublicationCandidate = {
  document_id: string;
  title: string;
  project: string;
  version: string;
  valid_from: string | null;
};

type ReviewItem = {
  document_id: string;
  title: string;
  project_id: string;
  project: string;
  client: string | null;
  year: number | null;
  domain: string;
  role: string;
  version: string;
  is_final: boolean;
  knowledge_status: string;
  confidentiality: string;
  page_count: number;
  extracted_chunk_count: number;
  citation_basis: string;
  source_available: boolean;
  preview_available: boolean;
  preview_kind: "pdf" | "image" | "text" | "video" | null;
  issue: string | null;
  review_state: string;
  uploader_name: string;
  uploader_username: string | null;
  upload_source: "web" | "nas";
  pending_proposal: ReviewProposalItem | null;
  metadata_confirmed: boolean;
  confirm_eligible: boolean;
  confirm_blockers: string[];
  publication_eligible: boolean;
  publication_blockers: string[];
  replacement_candidates: PublicationCandidate[];
};

type GovernanceSuggestion = {
  level: string;
  confidence: "high" | "medium" | "low";
  reason: string;
  requires_manual_review: boolean;
  needs_review: boolean;
};

type GovernanceDocument = {
  document_id: string;
  title: string;
  project: string;
  domain: string;
  role: string;
  version: string;
  knowledge_status: string;
  confidentiality: string;
  page_count: number;
  preview_available: boolean;
  source_available: boolean;
  ai_suggestion: GovernanceSuggestion;
};

type GovernanceResponse = {
  items: GovernanceDocument[];
  total: number;
  offset: number;
  limit: number;
  counts: Record<string, number>;
  manual_review_count: number;
};

type GovernanceAIReport = {
  dry_run: boolean;
  scanned_count: number;
  proposed_change_count?: number;
  changed_count?: number;
  proposed_counts?: Record<string, number>;
  changed_counts?: Record<string, number>;
  manual_review_count: number;
  notice?: string;
};

type UploadResult = {
  filename: string;
  department: string;
  confidentiality: string;
  size_bytes: number;
  status: string;
  document_id: string | null;
  review_required: boolean;
  duplicate_filtered: boolean;
  notice: string;
};

type UploadRequestError = Error & {
  status?: number;
};

type ContractCategory = {
  key: "administrative" | "personnel" | "business" | "executive_office";
  name: string;
  confidentiality: "L4" | "L5";
  can_search: boolean;
  can_upload: boolean;
  search_scope: "own" | "all" | null;
};

type ContractDocument = {
  document_id: string;
  title: string;
  folder_path: string;
  version: string;
  page_count: number;
  citation_basis: string;
  knowledge_status: string;
  confidentiality: string;
  created_at: string;
};

type ContractArchiveResponse = {
  category: string;
  category_name: string;
  confidentiality: string;
  pending_count: number;
  items: ContractDocument[];
};

type OwnedContractDocument = ContractDocument & {
  category: ContractCategory["key"];
  category_name: string;
  status_label: string;
  source_available: boolean;
  can_move: boolean;
};

type OwnedContractResponse = {
  count: number;
  items: OwnedContractDocument[];
};

type InboxIssue = {
  id: string;
  relative_path: string;
  status: string;
  error_code: string;
  message: string;
  size_bytes: number;
  last_seen_at: string;
};

type WritingResponse = {
  draft: string;
  sources: SearchResult[];
  generation_mode: "llm" | "local_evidence" | "local_only";
  generation_model: string | null;
  generation_degraded: boolean;
  retrieval_mode: string;
  retrieval_degraded: boolean;
  effective_category: string | null;
  effective_category_name: string | null;
  category_auto_inferred: boolean;
  restricted_source_count: number;
  l3_authorized_for_request: boolean;
  notice: string;
};

type WritingDraftRecord = {
  id: string;
  title: string;
  instruction: string;
  draft: string;
  response: WritingResponse | null;
  category?: string | null;
  scope?: string;
  time_scope?: string;
  generation_mode?: string | null;
  generation_model?: string | null;
  sources?: SearchResult[];
  kind?: "latest" | "saved";
  auto_saved?: boolean;
  created_at: string;
  updated_at: string;
};

type WritingDraftRegistry = {
  latest: WritingDraftRecord | null;
  saved: WritingDraftRecord[];
  saved_count: number;
  max_saved: number;
};

type EvolutionSource = {
  document_id: string;
  title: string;
  version: string;
  role: string;
  page: number | null;
  excerpt: string | null;
  effective_at: string;
  project: {
    id: string;
    name: string;
    client: string | null;
    year: number | null;
    domain: string;
  };
  confidentiality: string;
  source_available: boolean;
};

type EvolutionCandidate = {
  candidate_id: string;
  target_section: string;
  suggested_action: string;
  classification: "material" | "review" | "defer" | "blocked" | "conflict";
  score_band: "material" | "review" | "defer";
  score: number;
  score_breakdown: Record<string, number>;
  primary_source: EvolutionSource;
  corroborating_sources: EvolutionSource[];
  disclosure_status: string;
  hard_gate_failures: string[];
  confidence: string;
  reason_new: string;
};

type EvolutionDigest = {
  artifact: { type: string; name: string; audience: string };
  cutoff_date: string;
  reviewed_through: string;
  generated_at: string;
  eligible_count: number;
  publishable_count: number;
  material_count: number;
  review_count: number;
  deferred_count: number;
  blocked_count: number;
  conflict_count: number;
  duplicate_count: number;
  excluded_counts: Record<string, number>;
  candidates: EvolutionCandidate[];
  missing_evidence: { document_id: string; title: string; reason: string }[];
  next_action: string;
  automatic_publication: false;
  generation_mode: string;
};

type EvolutionBaselineDocument = {
  id: string;
  title: string;
  version: string;
  effective_at: string;
  project: string;
  confidentiality: string;
  supersedes_document_id: string | null;
  source_available: boolean;
};

type EvolutionChangePlan = {
  id: string;
  run_id: string;
  artifact_id: string;
  status: string;
  version: number;
  source_fingerprint: string;
  plan: {
    accepted_count: number;
    publication_status: string;
    next_action: string;
    changes: {
      candidate_id: string;
      target_section: string;
      action: string;
      proposed_content: string | null;
      reason: string | null;
      confidence: string | null;
      score: number;
      evidence: { primary_source: EvolutionSource };
    }[];
  };
  automatic_publication: false;
  created_at: string;
  updated_at: string;
};

type EvolutionRunSummary = {
  id: string;
  artifact_id: string;
  cutoff_date: string;
  reviewed_through: string;
  confidentiality: string;
  status: string;
  generation_mode: string;
  summary: Omit<EvolutionDigest, "candidates" | "missing_evidence"> & {
    persisted_candidate_count: number;
    missing_evidence_count: number;
  };
  change_plan: EvolutionChangePlan | null;
  automatic_publication: false;
  reviewed_at: string | null;
  created_at: string;
};

type PersistedEvolutionCandidate = EvolutionCandidate & {
  id: string;
  run_id: string;
  candidate_key: string;
  review_status: "pending" | "accepted" | "rejected" | "deferred";
  decision_note: string | null;
  decided_at: string | null;
  created_at: string;
};

type EvolutionReviewRun = EvolutionRunSummary & {
  candidates: PersistedEvolutionCandidate[];
};

type MaintainedArtifact = {
  id: string;
  name: string;
  artifact_type: string;
  artifact_type_label: string;
  current_document: {
    id: string;
    title: string;
    version: string;
    effective_at: string;
  } | null;
  owner: { id: string; display_name: string } | null;
  audience: "internal" | "external";
  confidentiality: string;
  cutoff_date: string;
  review_cadence_days: number;
  next_review_at: string;
  last_reviewed_at: string | null;
  section_map: Record<string, string>;
  status: string;
  automatic_publication: false;
  created_at: string;
  updated_at: string;
  runs?: EvolutionRunSummary[];
};

type Tab = "工作台" | "财务分析" | "项目管理" | "资料上传" | "合同档案库" | "AI资料检索" | "智能创作" | "入库审核" | "资料治理" | "知识进化" | "系统状态" | "账号管理";

// 评测题库与知识进化暂不作为产品功能开放。保留历史数据和实现，
// 但不展示入口、不发起请求，便于未来按真实业务需要重新评估。
const ADVANCED_GOVERNANCE_ENABLED = false;

const tabs: { name: Tab; icon: string }[] = [
  { name: "工作台", icon: "⌂" },
  { name: "财务分析", icon: "¥" },
  { name: "项目管理", icon: "▦" },
  { name: "资料上传", icon: "↑" },
  { name: "合同档案库", icon: "▣" },
  { name: "AI资料检索", icon: "✦" },
  { name: "智能创作", icon: "✎" },
  { name: "入库审核", icon: "✓" },
  { name: "资料治理", icon: "◆" },
  { name: "系统状态", icon: "◎" },
  { name: "账号管理", icon: "人" },
];

const mobilePrimaryTabNames: Tab[] = ["工作台", "AI资料检索", "智能创作", "资料上传"];

const defaultCategoryNames: Record<string, string> = {
  training: "电竞培训",
  company: "公司资料",
  venue: "场馆运营",
  youth: "电竞青训",
  team: "电竞战队",
  tournament: "电竞赛事",
};

const roleNames: Record<string, string> = {
  company_profile: "公司介绍",
  proposal: "提案",
  execution: "执行材料",
  brief: "客户Brief",
  closing_report: "结案报告",
  asset: "素材",
  contract: "合同",
};

const userRoleNames: Record<string, string> = {
  founder: "创始人",
  employee: "员工",
  planner: "员工",
  department_owner: "业务负责人",
  knowledge_admin: "资料管理员",
  administrative: "行政",
  personnel: "人事",
  business: "业务",
  education: "教培",
  finance: "财务",
  management: "管理",
};

const confidentialityNames: Record<string, string> = {
  L1: "公司公共资料",
  L2: "业务普通资料",
  L3: "业务敏感资料",
  L4: "核心敏感资料",
  L5: "公司最高机密",
};

const COST_CENTER_OPTIONS = [
  ["CC26A01", "薪资社保"],
  ["CC26A02", "税费及财务费用"],
  ["CC26A03", "差旅"],
  ["CC26A04", "现金科目"],
  ["CC26A05", "总部招待"],
  ["CC26A06", "总部酒水"],
  ["CC26A07", "总部办公费用"],
  ["CC26A08", "总部车辆费用"],
  ["CC26A09", "总部装修费用"],
  ["CC26A10", "出借款"],
  ["CC26A11", "短信验证"],
  ["CC26B01", "KPL青训"],
  ["CC26B02", "KPL上海大培训"],
  ["CC26B03", "王者国家队集训"],
  ["CC26B04", "LPL青训"],
  ["CC26B05", "三角洲国际战队培训"],
  ["CC26B06", "后勤保障项目"],
  ["CC26B07", "德玛西亚杯"],
  ["CC26B08", "杭州童雅"],
  ["CC26B09", "上海业务"],
  ["CC26C01", "智子费用"],
  ["CC26C02", "商演项目"],
  ["CC26C03", "备用金"],
  ["CC26C04", "西安回款"],
  ["CC26C05", "国外战队奖金"],
] as const;

const COST_CENTER_CODE_PATTERN = "CC[0-9]{2}[A-C][0-9]{2}";

function isCostCenterCode(value: string): boolean {
  return /^CC\d{2}[A-C]\d{2}$/.test(value.trim().toUpperCase());
}

function confidentialityLabel(level: string): string {
  return `${level} · ${confidentialityNames[level] || level}`;
}

const moneyFormatter = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 2,
});

function formatMoney(value: MoneyValue): string {
  const amount = Number(value || 0);
  return moneyFormatter.format(Number.isFinite(amount) ? amount : 0);
}

function executionTeamMembers(project: Pick<ManagedProject, "manager" | "members">): string[] {
  const managerName = project.manager.trim().toLocaleLowerCase("zh-CN");
  const seen = new Set<string>();
  return (project.members || []).map((member) => member.trim()).filter((member) => {
    const normalized = member.toLocaleLowerCase("zh-CN");
    if (!member || normalized === managerName || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
}

function executionTeamSummary(project: Pick<ManagedProject, "manager" | "members">): string {
  const members = executionTeamMembers(project);
  if (!members.length) return "待补充";
  return `${members.slice(0, 3).join("、")}${members.length > 3 ? ` 等 ${members.length} 人` : ""}`;
}

const contractAlertProjectStatuses = new Set(["active", "closing_review", "closing_rejected", "closed", "archived"]);

function managedProjectContractStatus(project: ManagedProject): "unsigned" | "signed_received" {
  return project.contract_status === "signed_received" ? "signed_received" : "unsigned";
}

function managedProjectContractAlert(project: ManagedProject): boolean {
  if (typeof project.contract_alert === "boolean") return project.contract_alert;
  if (typeof project.contract_unsigned_alert === "boolean") return project.contract_unsigned_alert;
  return contractAlertProjectStatuses.has(project.status) && managedProjectContractStatus(project) === "unsigned";
}

function managedProjectContractLabel(project: ManagedProject): string {
  return managedProjectContractStatus(project) === "signed_received" ? "已签署收件" : "未签署";
}

type FinanceAlert = FinanceDashboard["anomalies"][number];

function financeAlertCategory(item: FinanceAlert): "business" | "data-quality" {
  const signal = [item.alert_type, item.rule_code, ...(item.rule_codes || []), ...(item.reasons || [])].filter(Boolean).join(" ").toLowerCase();
  const dataQualitySignals = [
    "data_quality", "data-quality", "data_integrity", "suspected_duplicate", "missing_", "invalid_",
    "balance_continuity", "balance_discontinuity", "dual_amount", "dual_direction", "zero_amount", "negative_amount",
    "字段缺失", "信息不完整", "格式异常", "金额异常", "借贷同时", "余额不连续", "日期异常", "摘要缺失",
    "往来单位缺失", "对方单位缺失", "疑似重复", "出现负数", "同时存在收入和支出", "金额均为零",
  ];
  return dataQualitySignals.some((keyword) => signal.includes(keyword)) ? "data-quality" : "business";
}

function financeAlertLabel(item: FinanceAlert): string {
  const signal = [item.alert_type, item.rule_code, ...(item.rule_codes || []), ...(item.reasons || [])].filter(Boolean).join(" ").toLowerCase();
  if (signal.includes("new_counterparty") || signal.includes("first_counterparty") || signal.includes("首次出现")) return "首次出现往来单位";
  if (signal.includes("behavior_change") || signal.includes("historical_deviation") || signal.includes("历史行为突变")) return "历史行为突变";
  if (signal.includes("oa_missing") || signal.includes("unapproved_expense") || signal.includes("无审批支出")) return "飞书 OA 审批未匹配";
  if (signal.includes("approval_amount") || signal.includes("金额超审批")) return "支出金额超过审批";
  if (signal.includes("payee_mismatch") || signal.includes("收款方不一致")) return "收款方与审批不一致";
  if (signal.includes("balance_continuity") || signal.includes("余额不连续")) return "余额连续性校验异常";
  if (signal.includes("suspected_duplicate") || signal.includes("疑似重复")) return "疑似重复流水";
  if (signal.includes("negative_amount") || signal.includes("出现负数")) return "收支金额字段异常";
  if (signal.includes("zero_amount") || signal.includes("金额均为零")) return "零金额流水待核验";
  if (signal.includes("missing_counterparty") || signal.includes("往来单位缺失")) return "往来单位信息缺失";
  if (signal.includes("missing_summary") || signal.includes("摘要缺失")) return "流水摘要信息缺失";
  if (signal.includes("dual_amount") || signal.includes("借贷同时")) return "借贷金额字段冲突";
  return financeAlertCategory(item) === "data-quality" ? "数据质量待核验" : "业务行为待核验";
}

function FinanceRankingPanel({
  eyebrow,
  title,
  range,
  items,
  direction,
  emptyText,
}: {
  eyebrow: string;
  title: string;
  range: string;
  items: FinanceRankItem[];
  direction: "income" | "expense";
  emptyText: string;
}) {
  const rankMax = Math.max(1, ...items.map((item) => Number(item.amount) || 0));
  const directionLabel = direction === "income" ? "收入" : "支出";

  return (
    <section className={`panel financeRankingPanel ${direction}RankingPanel`}>
      <PanelTitle eyebrow={eyebrow} title={title} />
      <span className="financePanelRange">{range} · 已确认银行流水</span>
      <div className="financeRankList">
        {items.map((item, index) => (
          <article key={item.name}>
            <b>{index + 1}</b>
            <div>
              <strong title={item.name}>{item.name}</strong>
              <i><span style={{ width: `${Math.max(3, (Number(item.amount) || 0) / rankMax * 100)}%` }} /></i>
              <small>{item.transaction_count} 笔{directionLabel}</small>
            </div>
            <em className={direction === "income" ? "financeIncomeAmount" : "financeExpenseAmount"}>{formatMoney(item.amount)}</em>
          </article>
        ))}
        {!items.length && <p className="mutedText">{emptyText}</p>}
      </div>
    </section>
  );
}

function FinanceAlertsPanel({
  eyebrow,
  title,
  range,
  periodLabel,
  count,
  items,
  onSelectBatch,
}: {
  eyebrow: string;
  title: string;
  range: string;
  periodLabel: string;
  count: number;
  items: FinanceAlertItem[];
  onSelectBatch: (batchId: string) => Promise<void>;
}) {
  return (
    <section className="panel financeAnomalyPanel">
      <PanelTitle eyebrow={eyebrow} title={title} />
      <p className="financeAlertIntro">经营排行展示收支规模，本栏只呈现需要核验的业务变化与数据问题，不因金额较大而直接判定异常。</p>
      <div className="financeAlertRuleChips" aria-label={`${periodLabel}预警规则`}>
        <span>首次出现往来单位</span>
        <span>历史行为突变</span>
        <span>数据质量校验</span>
      </div>
      <div className="financeOaRoadmap">
        <strong>当前未接入飞书 OA</strong>
        <span>现阶段不执行审批流匹配；接入后再校验无审批支出、金额超审批及收款方不一致。</span>
      </div>
      <span className="financePanelRange">
        {range} · 已确认银行流水 · 共 {count} 条待核验事项
        {count > items.length ? ` · 显示优先级最高的 ${items.length} 条` : ""}
      </span>
      <div className="financeAnomalyList">
        {items.map((item) => {
          const category = financeAlertCategory(item);
          return (
            <article key={item.id} className={`${item.severity} ${category}`}>
              <div className="anomalyHeading">
                <div>
                  <span className={`alertKindBadge ${category}`}>{category === "business" ? "业务预警" : "数据质量"}</span>
                  <b>{financeAlertLabel(item)}</b>
                </div>
                <time>{item.transaction_date}</time>
              </div>
              <strong>{item.counterparty || "往来单位待补全"}</strong>
              <p>{(item.reasons || []).join(" · ") || "该笔流水需要人工核验。"}</p>
              <small title={item.summary || ""}>{item.summary || "流水摘要待补全"}</small>
              <footer>
                <b className={Number(item.income) > 0 ? "financeIncomeAmount" : "financeExpenseAmount"}>{Number(item.income) > 0 ? "收入 " : "支出 "}{formatMoney(item.amount)}</b>
                <span>{item.status === "confirmed" ? "已确认" : "待确认"}</span>
                <button type="button" onClick={() => void onSelectBatch(item.batch_id)}>查看流水</button>
              </footer>
            </article>
          );
        })}
        {!items.length && (
          <div className="financeNoAnomaly">
            <b>✓</b>
            <span>{periodLabel}没有需要核验的风险或数据质量问题</span>
            <small>经营排行中的大额收支不会自动标记为异常。</small>
          </div>
        )}
      </div>
    </section>
  );
}

function formatChineseDateRange(start: string, end: string): string {
  const parse = (value: string) => {
    const [year, month, day] = value.split("-").map(Number);
    return { year, month, day };
  };
  const from = parse(start);
  const to = parse(end);
  if (!from.month || !from.day || !to.month || !to.day) return `${start} 至 ${end}`;
  if (from.year === to.year && from.month === to.month) {
    return `${from.month}月${from.day}日至${to.day}日`;
  }
  if (from.year === to.year) {
    return `${from.month}月${from.day}日至${to.month}月${to.day}日`;
  }
  return `${from.year}年${from.month}月${from.day}日至${to.year}年${to.month}月${to.day}日`;
}

function formatShanghaiDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value));
}

function toShanghaiDateTimeLocal(value: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}:${part("second")}`;
}

const managedProjectStatusNames: Record<string, string> = {
  draft: "立项草稿",
  initiation_review: "立项复核中",
  initiation_rejected: "立项已退回",
  active: "执行中",
  closing_review: "结案复核中",
  closing_rejected: "结案已退回",
  closed: "已结案",
  archived: "已归档",
};

const TOKEN_KEY = "jingao-kb-session";
const BATCH_REVIEW_CHUNK_SIZE = 50;
const SHANGHAI_TODAY = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
}).format(new Date());

function apiErrorMessage(payload: unknown, status: number): string {
  const detail = (
    payload && typeof payload === "object" && "detail" in payload
      ? (payload as { detail?: unknown }).detail
      : undefined
  );
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const value = item as { msg?: unknown; message?: unknown };
        if (typeof value.msg === "string") return value.msg;
        if (typeof value.message === "string") return value.message;
      }
      return "请求内容不符合要求";
    });
    return Array.from(new Set(messages)).join("；");
  }
  if (detail && typeof detail === "object") {
    const value = detail as { msg?: unknown; message?: unknown };
    if (typeof value.msg === "string") return value.msg;
    if (typeof value.message === "string") return value.message;
  }
  return `请求失败（${status}）`;
}

async function kbFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  if (token) headers.set("authorization", `Bearer ${token}`);
  const response = await fetch(`/api/kb/${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(apiErrorMessage(payload, response.status));
  }
  return payload as T;
}

async function kbFormFetch<T>(
  path: string,
  body: FormData,
  token: string,
): Promise<T> {
  const response = await fetch(`/api/kb/${path}`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}` },
    body,
    cache: "no-store",
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(apiErrorMessage(payload, response.status));
  return payload as T;
}

function writingTitle(draft: string, instruction: string) {
  const heading = draft
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => /^#{1,3}\s+/.test(line));
  const raw = (heading?.replace(/^#{1,3}\s+/, "") || instruction.trim().split(/\r?\n/)[0] || "智能创作初稿")
    .replace(/\[S\d+\]/g, "")
    .replace(/[*_`~]/g, "")
    .trim();
  return raw.slice(0, 40) || "智能创作初稿";
}

function safeWritingFilename(title: string) {
  const safe = title
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
    .replace(/\s+/g, " ")
    .replace(/[. ]+$/g, "")
    .trim()
    .slice(0, 56) || "智能创作初稿";
  const day = new Date().toLocaleDateString("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).replaceAll("/", "-");
  return `${safe}-${day}.md`;
}

function parseBusinessGoldCases(value: string): Record<string, unknown>[] {
  const trimmed = value.trim();
  if (!trimmed) throw new Error("请先粘贴 JSON 数组或 JSONL 内容");
  if (trimmed.startsWith("[")) {
    const payload = JSON.parse(trimmed);
    if (!Array.isArray(payload)) throw new Error("JSON 内容必须是题目数组");
    return payload;
  }
  return trimmed.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

export default function Home() {
  const [active, setActive] = useState<Tab>("工作台");
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [reviewQueue, setReviewQueue] = useState<ReviewItem[]>([]);
  const [inboxIssues, setInboxIssues] = useState<InboxIssue[]>([]);
  const [accounts, setAccounts] = useState<AdminUser[]>([]);
  const [categories, setCategories] = useState<KnowledgeCategory[]>([]);
  const [operations, setOperations] = useState<OperationsStatus | null>(null);
  const [businessGold, setBusinessGold] = useState<BusinessGoldRegistry | null>(null);
  const [businessGoldSources, setBusinessGoldSources] = useState<BusinessGoldSource[]>([]);
  const [businessGoldSelected, setBusinessGoldSelected] = useState<string[]>([]);
  const [businessGoldBulk, setBusinessGoldBulk] = useState("");
  const [businessGoldMessage, setBusinessGoldMessage] = useState("");
  const [businessGoldBusy, setBusinessGoldBusy] = useState(false);
  const [businessGoldEditing, setBusinessGoldEditing] = useState<BusinessGoldCase | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [question, setQuestion] = useState("");
  const [submittedSearchQuery, setSubmittedSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchingMore, setSearchingMore] = useState(false);
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [writingBusy, setWritingBusy] = useState(false);
  const [writingError, setWritingError] = useState("");
  const [writingResponse, setWritingResponse] = useState<WritingResponse | null>(null);
  const [writingInstruction, setWritingInstruction] = useState("");
  const [writingDraftText, setWritingDraftText] = useState("");
  const [writingDraftView, setWritingDraftView] = useState<"preview" | "edit">("preview");
  const [writingDrafts, setWritingDrafts] = useState<WritingDraftRegistry>({
    latest: null,
    saved: [],
    saved_count: 0,
    max_saved: 5,
  });
  const [writingDraftBusy, setWritingDraftBusy] = useState("");
  const [writingDraftMessage, setWritingDraftMessage] = useState("");
  const [writingActiveDraftKind, setWritingActiveDraftKind] = useState<"latest" | "saved" | null>(null);
  const [writingLatestEditPending, setWritingLatestEditPending] = useState(false);
  const [categoryBusy, setCategoryBusy] = useState("");
  const [evolutionBusy, setEvolutionBusy] = useState(false);
  const [evolutionDigest, setEvolutionDigest] = useState<EvolutionDigest | null>(null);
  const [evolutionArtifacts, setEvolutionArtifacts] = useState<MaintainedArtifact[]>([]);
  const [evolutionBaselines, setEvolutionBaselines] = useState<EvolutionBaselineDocument[]>([]);
  const [selectedEvolutionArtifact, setSelectedEvolutionArtifact] = useState<MaintainedArtifact | null>(null);
  const [evolutionRun, setEvolutionRun] = useState<EvolutionReviewRun | null>(null);
  const [evolutionMessage, setEvolutionMessage] = useState("");
  const [evolutionActionBusy, setEvolutionActionBusy] = useState("");
  const [previewBusy, setPreviewBusy] = useState("");
  const [reviewEditing, setReviewEditing] = useState("");
  const [reviewBusy, setReviewBusy] = useState("");
  const [reviewMessage, setReviewMessage] = useState("");
  const [selectedReviewIds, setSelectedReviewIds] = useState<string[]>([]);
  const [governance, setGovernance] = useState<GovernanceResponse | null>(null);
  const [governanceSelected, setGovernanceSelected] = useState<string[]>([]);
  const [governanceQuery, setGovernanceQuery] = useState("");
  const [governanceDomain, setGovernanceDomain] = useState("");
  const [governanceLevel, setGovernanceLevel] = useState("");
  const [governanceRole, setGovernanceRole] = useState("");
  const [governanceManualOnly, setGovernanceManualOnly] = useState(false);
  const [governanceTarget, setGovernanceTarget] = useState("L2");
  const [governanceReason, setGovernanceReason] = useState("AI初筛后的人工密级治理");
  const [governanceBusy, setGovernanceBusy] = useState("");
  const [governanceMessage, setGovernanceMessage] = useState("");
  const [governanceAIReport, setGovernanceAIReport] = useState<GovernanceAIReport | null>(null);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadFolderName, setUploadFolderName] = useState("");
  const [uploadDepartment, setUploadDepartment] = useState("training");
  const [uploadConfidentiality, setUploadConfidentiality] = useState("L2");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadMessage, setUploadMessage] = useState("");
  const [contractCategories, setContractCategories] = useState<ContractCategory[]>([]);
  const [contractCategory, setContractCategory] = useState("");
  const [contractCategoriesLoading, setContractCategoriesLoading] = useState(false);
  const [contractCategoriesError, setContractCategoriesError] = useState("");
  const [contractCategoriesReloadKey, setContractCategoriesReloadKey] = useState(0);
  const [contractDocuments, setContractDocuments] = useState<ContractDocument[]>([]);
  const [ownedContractDocuments, setOwnedContractDocuments] = useState<OwnedContractDocument[]>([]);
  const [contractFolders, setContractFolders] = useState<Record<string, string[]>>({});
  const [contractNewFolderCategory, setContractNewFolderCategory] = useState("");
  const [contractNewFolderPath, setContractNewFolderPath] = useState("");
  const [contractMoveCategories, setContractMoveCategories] = useState<Record<string, ContractCategory["key"]>>({});
  const [contractMoveTargets, setContractMoveTargets] = useState<Record<string, string>>({});
  const [contractMoveErrors, setContractMoveErrors] = useState<Record<string, string>>({});
  const [contractManageBusy, setContractManageBusy] = useState("");
  const [contractPendingCount, setContractPendingCount] = useState(0);
  const [contractQuery, setContractQuery] = useState("");
  const [contractSearchResponse, setContractSearchResponse] = useState<SearchResponse | null>(null);
  const [contractFiles, setContractFiles] = useState<File[]>([]);
  const [contractSelectionMode, setContractSelectionMode] = useState<"files" | "folder">("files");
  const [contractFolderName, setContractFolderName] = useState("");
  const [contractUploadProgress, setContractUploadProgress] = useState({ completed: 0, total: 0 });
  const [contractBusy, setContractBusy] = useState(false);
  const [contractMessage, setContractMessage] = useState("");
  const [financeEntities, setFinanceEntities] = useState<FinanceEntity[]>([]);
  const [selectedFinanceEntityId, setSelectedFinanceEntityId] = useState("");
  const [financeDashboard, setFinanceDashboard] = useState<FinanceDashboard | null>(null);
  const [financePeriodView, setFinancePeriodView] = useState<"realtime" | number>("realtime");
  const [financeAnnualYears, setFinanceAnnualYears] = useState<number[]>([]);
  const [financeAnnualDashboard, setFinanceAnnualDashboard] = useState<FinanceAnnualDashboard | null>(null);
  const [financeBatches, setFinanceBatches] = useState<FinanceBatch[]>([]);
  const [financeCash, setFinanceCash] = useState<CashLedgerEntry[]>([]);
  const [financeTransfers, setFinanceTransfers] = useState<FinanceInternalTransferRegistry>({
    confirmed_amount: 0,
    candidate_amount: 0,
    confirmed_count: 0,
    candidate_count: 0,
    items: [],
  });
  const [financeIncludeInternalTransfers, setFinanceIncludeInternalTransfers] = useState(false);
  const [selectedFinanceBatch, setSelectedFinanceBatch] = useState("");
  const [financeTransactions, setFinanceTransactions] = useState<FinanceTransaction[]>([]);
  const [financePurposeCorrections, setFinancePurposeCorrections] = useState<FinancePurposeCorrectionRegistry>({
    items: [],
    pending_count: 0,
    approved_count: 0,
    rejected_count: 0,
  });
  const [financeBusy, setFinanceBusy] = useState("");
  const [financeMessage, setFinanceMessage] = useState("");
  const [financeUploadError, setFinanceUploadError] = useState("");
  const [managedProjects, setManagedProjects] = useState<ManagedProjectRegistry>({ counts: {}, portfolio_counts: {}, items: [] });
  const [selectedManagedProject, setSelectedManagedProject] = useState<ManagedProject | null>(null);
  const [projectCollaboratorCandidates, setProjectCollaboratorCandidates] = useState<ProjectCollaboratorAccount[]>([]);
  const [projectBusy, setProjectBusy] = useState("");
  const [projectModule, setProjectModule] = useState<"standard" | "education" | "education-ledger">("standard");
  const [projectMessage, setProjectMessage] = useState("");
  const [projectDeletePasswordConfigured, setProjectDeletePasswordConfigured] = useState<boolean | null>(null);
  const [inboxScanBusy, setInboxScanBusy] = useState(false);
  const [inboxIssueBusy, setInboxIssueBusy] = useState("");
  const [accountBusy, setAccountBusy] = useState("");
  const [evaluationBusy, setEvaluationBusy] = useState(false);
  const [concurrencyBusy, setConcurrencyBusy] = useState(false);
  const [sourceReconcileBusy, setSourceReconcileBusy] = useState(false);
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const searchResultRef = useRef<HTMLDivElement | null>(null);
  const writingResultRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileMenuOpen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [mobileMenuOpen]);

  function navigateToTab(tab: Tab) {
    setActive(tab);
    setMobileMenuOpen(false);
  }

  function scrollToMobileResult(target: { current: HTMLDivElement | null }) {
    if (typeof window === "undefined" || !window.matchMedia("(max-width: 760px)").matches) return;
    window.requestAnimationFrame(() => {
      target.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  const loadWorkspace = useCallback(async (activeToken: string) => {
    const me = await kbFetch<User>("v1/me", {}, activeToken);
    const canReview = ["founder", "knowledge_admin", "department_owner"].includes(me.role);
    const canOperate = ["founder", "knowledge_admin"].includes(me.role);
    const canEvolve = ADVANCED_GOVERNANCE_ENABLED && canOperate;
    const canGovern = ["founder", "knowledge_admin"].includes(me.role);
    const confidentialityRank = ({ L1: 1, L2: 2, L3: 3, L4: 4, L5: 5 } as Record<string, number>)[me.confidentiality_ceiling] || 1;
    const canUseContracts = confidentialityRank >= 4
      && ["administrative", "personnel", "finance", "management"].includes(me.organization_role);
    const canUseFinance = (
      (me.organization_role === "finance" && confidentialityRank >= 4)
      || (me.organization_role === "management" && confidentialityRank >= 5)
    );
    const canUseProjects = (
      me.organization_role === "business"
      || me.organization_role === "education"
      || (me.organization_role === "finance" && confidentialityRank >= 4)
      || (me.organization_role === "management" && confidentialityRank >= 5)
    );
    const [
      service,
      categoryRows,
      projectRows,
      queue,
      inboxIssueRows,
      localAccounts,
      operationState,
      goldRegistry,
      goldSources,
      artifactRows,
      baselineRows,
      governanceRows,
      contractCategoryRows,
    ] = await Promise.all([
      kbFetch<Status>("v1/status", {}, activeToken),
      kbFetch<KnowledgeCategory[]>("v1/categories", {}, activeToken),
      kbFetch<Project[]>("v1/projects", {}, activeToken),
      canReview
        ? kbFetch<ReviewItem[]>("v1/review/queue", {}, activeToken)
        : Promise.resolve([]),
      me.role === "founder"
        ? kbFetch<InboxIssue[]>("v1/review/inbox/issues", {}, activeToken)
        : Promise.resolve([]),
      me.role === "founder"
        ? kbFetch<AdminUser[]>("v1/admin/users", {}, activeToken)
        : Promise.resolve([]),
      canOperate
        ? kbFetch<OperationsStatus>("v1/operations/status", {}, activeToken)
        : Promise.resolve(null),
      Promise.resolve(null),
      Promise.resolve([]),
      canEvolve
        ? kbFetch<MaintainedArtifact[]>("v1/evolution/artifacts", {}, activeToken)
        : Promise.resolve([]),
      canEvolve
        ? kbFetch<EvolutionBaselineDocument[]>(
            "v1/evolution/baseline-documents?artifact_type=company_profile",
            {},
            activeToken,
          )
        : Promise.resolve([]),
      canGovern
        ? kbFetch<GovernanceResponse>("v1/governance/documents?limit=50", {}, activeToken)
        : Promise.resolve(null),
      canUseContracts
        ? kbFetch<ContractCategory[]>("v1/contracts/categories", {}, activeToken)
        : Promise.resolve([]),
    ]);
    setUser(me);
    const uploadDepartments = categoryRows
      .filter((item) => item.active)
      .map((item) => item.key);
    setUploadDepartment((current) => (
      uploadDepartments.includes(current) ? current : uploadDepartments[0] || "training"
    ));
    if (confidentialityRank < 2) {
      setUploadConfidentiality("L1");
    }
    setStatus(service);
    setCategories(categoryRows);
    setProjects(projectRows);
    setReviewQueue(queue);
    setInboxIssues(inboxIssueRows);
    setAccounts(localAccounts);
    setOperations(operationState);
    setBusinessGold(goldRegistry);
    setBusinessGoldSources(goldSources);
    setEvolutionArtifacts(artifactRows);
    setEvolutionBaselines(baselineRows);
    setGovernance(governanceRows);
    setContractCategories(contractCategoryRows);
    setContractCategoriesError("");
    setContractCategory((current) => (
      contractCategoryRows.some((item) => item.key === current)
        ? current
        : contractCategoryRows.find((item) => item.can_search)?.key
          || contractCategoryRows[0]?.key
          || ""
    ));
    setSelectedEvolutionArtifact((current) => (
      artifactRows.find((item) => item.id === current?.id) || null
    ));
    setActive((current) => (
      (!canReview && current === "入库审核")
      || (!canGovern && current === "资料治理")
      || (!canEvolve && current === "知识进化")
      || (!canOperate && current === "系统状态")
      || (me.role !== "founder" && current === "账号管理")
      || (!canUseContracts && current === "合同档案库")
      || (!canUseFinance && current === "财务分析")
      || (!canUseProjects && current === "项目管理")
        ? "工作台"
        : current
    ));
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function restoreSession() {
      await Promise.resolve();
      const saved = sessionStorage.getItem(TOKEN_KEY);
      if (!saved) {
        if (!cancelled) setInitializing(false);
        return;
      }
      if (cancelled) return;
      setToken(saved);
      try {
        await loadWorkspace(saved);
      } catch {
        sessionStorage.removeItem(TOKEN_KEY);
        if (!cancelled) {
          setToken("");
          setUser(null);
        }
      } finally {
        if (!cancelled) setInitializing(false);
      }
    }
    void restoreSession();
    return () => {
      cancelled = true;
    };
  }, [loadWorkspace]);

  useEffect(() => {
    if (!token || active !== "合同档案库") return;
    let cancelled = false;
    setContractCategoriesLoading(true);
    setContractCategoriesError("");
    void kbFetch<ContractCategory[]>("v1/contracts/categories", {}, token).then((rows) => {
      if (cancelled) return;
      if (rows.length === 0) throw new Error("当前账号没有返回可用的合同分类");
      setContractCategories(rows);
      setContractCategory((current) => (
        rows.some((item) => item.key === current)
          ? current
          : rows.find((item) => item.can_search)?.key || rows[0]?.key || ""
      ));
      setContractCategoriesError("");
    }).catch((cause) => {
      if (cancelled) return;
      setContractCategoriesError(cause instanceof Error ? cause.message : "合同权限加载失败");
    }).finally(() => {
      if (!cancelled) setContractCategoriesLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [active, contractCategoriesReloadKey, token]);

  useEffect(() => {
    if (!token || active !== "合同档案库" || !contractCategory) return;
    const selected = contractCategories.find((item) => item.key === contractCategory);
    if (!selected?.can_search) {
      return;
    }
    let cancelled = false;
    void kbFetch<ContractArchiveResponse>(
      `v1/contracts?category=${encodeURIComponent(contractCategory)}`,
      {},
      token,
    ).then((response) => {
      if (!cancelled) {
        setContractDocuments(response.items);
        setContractPendingCount(response.pending_count || 0);
      }
    }).catch((cause) => {
      if (!cancelled) {
        setError(cause instanceof Error ? cause.message : "合同档案加载失败");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [active, contractCategories, contractCategory, token]);

  useEffect(() => {
    if (!token || active !== "合同档案库" || contractCategories.length === 0) return;
    let cancelled = false;
    const uploadable = contractCategories.filter((item) => item.can_upload);
    void Promise.all([
      kbFetch<OwnedContractResponse>("v1/contracts/mine", {}, token),
      ...uploadable.map(async (item) => {
        const response = await kbFetch<{ category: string; items: string[] }>(
          `v1/contracts/folders?category=${encodeURIComponent(item.key)}`,
          {},
          token,
        );
        return response;
      }),
    ]).then(([mine, ...folderResponses]) => {
      if (cancelled) return;
      setOwnedContractDocuments(mine.items);
      setContractFolders(Object.fromEntries(folderResponses.map((item) => [item.category, item.items])));
      setContractNewFolderCategory((current) => current || uploadable[0]?.key || "");
    }).catch((cause) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : "本人合同清单加载失败");
    });
    return () => {
      cancelled = true;
    };
  }, [active, contractCategories, token]);

  useEffect(() => {
    if (!token || !user) return;
    const rank = ({ L1: 1, L2: 2, L3: 3, L4: 4, L5: 5 } as Record<string, number>)[user.confidentiality_ceiling] || 1;
    const allowed = (
      (user.organization_role === "finance" && rank >= 4)
      || (user.organization_role === "management" && rank >= 5)
    );
    if (!allowed) return;
    let cancelled = false;
    void kbFetch<FinanceEntity[]>("v1/finance/entities", {}, token).then((rows) => {
      if (cancelled) return;
      setFinanceEntities(rows);
      setSelectedFinanceEntityId((current) => (
        rows.some((item) => item.id === current)
          ? current
          : (rows.find((item) => item.key === "jingao")?.id || rows[0]?.id || "")
      ));
    }).catch((cause) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : "公司财务主体加载失败");
    });
    return () => {
      cancelled = true;
    };
  }, [token, user]);

  useEffect(() => {
    if (!token || active !== "财务分析" || !selectedFinanceEntityId) return;
    const selectedEntity = financeEntities.find((item) => item.id === selectedFinanceEntityId);
    if (!selectedEntity) return;
    let cancelled = false;
    const query = `?entity_id=${encodeURIComponent(selectedFinanceEntityId)}&include_internal_transfers=${financeIncludeInternalTransfers ? "true" : "false"}`;
    const transferQuery = `?entity_id=${encodeURIComponent(selectedFinanceEntityId)}`;
    setFinanceBusy("company");
    setSelectedFinanceBatch("");
    setFinanceTransactions([]);
    Promise.all([
      kbFetch<FinanceDashboard>(`v1/finance/dashboard${query}`, {}, token),
      kbFetch<FinanceBatch[]>(`v1/finance/statements${query}`, {}, token),
      selectedEntity.show_cash
        ? kbFetch<CashLedgerEntry[]>(`v1/finance/cash${query}`, {}, token)
        : Promise.resolve([] as CashLedgerEntry[]),
      kbFetch<FinanceInternalTransferApiRegistry>(`v1/finance/internal-transfers${transferQuery}&review_status=all&limit=100`, {}, token),
      kbFetch<FinanceAnnualYears>(`v1/finance/annual-years${transferQuery}`, {}, token),
      kbFetch<FinancePurposeCorrectionRegistry>(`v1/finance/purpose-corrections${transferQuery}&review_status=all&limit=100`, {}, token),
    ]).then(([dashboard, batches, cash, transfers, annualYears, purposeCorrections]) => {
      if (cancelled) return;
      setFinanceDashboard(dashboard);
      setFinanceBatches(batches);
      setFinanceCash(cash);
      setFinanceTransfers(normalizeFinanceTransferRegistry(transfers));
      setFinanceAnnualYears(annualYears.years);
      setFinancePurposeCorrections(purposeCorrections);
    }).catch((cause) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : "公司财务数据加载失败");
    }).finally(() => {
      if (!cancelled) setFinanceBusy("");
    });
    return () => {
      cancelled = true;
    };
  }, [active, financeEntities, financeIncludeInternalTransfers, selectedFinanceEntityId, token]);

  useEffect(() => {
    if (
      !token
      || active !== "财务分析"
      || !selectedFinanceEntityId
      || financePeriodView === "realtime"
    ) {
      setFinanceAnnualDashboard(null);
      return;
    }
    let cancelled = false;
    const query = `?entity_id=${encodeURIComponent(selectedFinanceEntityId)}&year=${financePeriodView}&include_internal_transfers=${financeIncludeInternalTransfers ? "true" : "false"}`;
    setFinanceBusy("annual");
    kbFetch<FinanceAnnualDashboard>(`v1/finance/annual${query}`, {}, token)
      .then((payload) => {
        if (!cancelled) setFinanceAnnualDashboard(payload);
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "年度财务数据加载失败");
      })
      .finally(() => {
        if (!cancelled) setFinanceBusy("");
      });
    return () => {
      cancelled = true;
    };
  }, [active, financeIncludeInternalTransfers, financePeriodView, selectedFinanceEntityId, token]);

  useEffect(() => {
    if (!token || active !== "项目管理" || user?.organization_role === "education"
      || (["education", "education-ledger"].includes(projectModule) && ["finance", "management"].includes(user?.organization_role || ""))) return;
    let cancelled = false;
    Promise.all([
      kbFetch<ManagedProjectRegistry>("v1/pm/projects", {}, token),
      user?.organization_role === "business"
        ? kbFetch<ProjectCollaboratorRegistry>("v1/pm/collaborator-candidates", {}, token)
        : Promise.resolve({ items: [] }),
    ]).then(([registry, collaboratorRegistry]) => {
      if (cancelled) return;
      setManagedProjects(registry);
      setProjectCollaboratorCandidates(collaboratorRegistry.items);
      setSelectedManagedProject((current) => (
        current && registry.items.some((item) => item.id === current.id) ? current : null
      ));
    }).catch((cause) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : "项目数据加载失败");
    }).finally(() => {
      if (!cancelled) setProjectBusy("");
    });
    return () => {
      cancelled = true;
    };
  }, [active, token, user?.organization_role, projectModule]);

  useEffect(() => {
    const isProjectFounder = Boolean(
      user?.organization_role === "management"
      && user?.confidentiality_ceiling === "L5"
      && ["found", "founder"].includes(user?.username.toLowerCase() || ""),
    );
    if (!token || active !== "项目管理" || !isProjectFounder) {
      setProjectDeletePasswordConfigured(null);
      return;
    }
    let cancelled = false;
    kbFetch<FounderDeletePasswordStatus>("v1/pm/founder-delete-password/status", {}, token)
      .then((status) => {
        if (!cancelled) setProjectDeletePasswordConfigured(status.configured);
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "项目删除密码状态加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [active, token, user?.confidentiality_ceiling, user?.organization_role, user?.username]);

  useEffect(() => {
    if (!token || active !== "智能创作") return;
    void loadWritingDrafts(true);
    // The API is reloaded whenever the user enters the writing workspace.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, token]);

  useEffect(() => {
    if (
      !token
      || active !== "智能创作"
      || writingActiveDraftKind !== "latest"
      || !writingLatestEditPending
      || !writingDraftText.trim()
      || writingInstruction.trim().length < 5
    ) return;
    const timer = window.setTimeout(() => {
      void kbFetch(
        "v1/writing/drafts/latest",
        {
          method: "PATCH",
          body: JSON.stringify({
            title: writingTitle(writingDraftText, writingInstruction),
            instruction: writingInstruction,
            draft: writingDraftText,
            category: writingResponse?.effective_category || null,
            scope: "all",
            generation_mode: writingResponse?.generation_mode || null,
            generation_model: writingResponse?.generation_model || null,
            sources: writingResponse?.sources || [],
            response: writingResponse ? { ...writingResponse, draft: writingDraftText } : null,
          }),
        },
        token,
      ).then(() => {
        setWritingLatestEditPending(false);
        setWritingDraftMessage("最近一次创作已自动保存。");
        void loadWritingDrafts();
      }).catch((cause) => {
        setWritingDraftMessage(cause instanceof Error ? cause.message : "自动保存暂时失败");
      });
    }, 1000);
    return () => window.clearTimeout(timer);
    // Only user edits mark the latest slot dirty; loading a saved item never overwrites it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, token, writingActiveDraftKind, writingLatestEditPending, writingDraftText]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [active]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoginBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const response = await kbFetch<{
        access_token: string;
        user: User;
      }>("v1/auth/login", {
        method: "POST",
        signal: AbortSignal.timeout(20_000),
        body: JSON.stringify({
          username: data.get("username"),
          password: data.get("password"),
        }),
      });
      sessionStorage.setItem(TOKEN_KEY, response.access_token);
      setToken(response.access_token);
      setUser(response.user);
      await loadWorkspace(response.access_token);
    } catch (cause) {
      setError(cause instanceof DOMException && cause.name === "TimeoutError"
        ? "登录服务响应超时，请稍后重试；无需更改密码。"
        : cause instanceof Error ? cause.message : "登录失败");
    } finally {
      setLoginBusy(false);
    }
  }

  async function handleLogout() {
    setMobileMenuOpen(false);
    try {
      await kbFetch("v1/auth/logout", { method: "POST" }, token);
    } catch {
      // Local session is cleared even if the API is restarting.
    }
    sessionStorage.removeItem(TOKEN_KEY);
    setToken("");
    setUser(null);
    setStatus(null);
    setReviewQueue([]);
    setSelectedReviewIds([]);
    setGovernance(null);
    setGovernanceSelected([]);
    setGovernanceMessage("");
    setGovernanceAIReport(null);
    setUploadFiles([]);
    setUploadMessage("");
    setUploadProgress(0);
    setFinanceDashboard(null);
    setFinanceBatches([]);
    setFinanceCash([]);
    setFinanceTransactions([]);
    setSelectedFinanceBatch("");
    setManagedProjects({ counts: {}, portfolio_counts: {}, items: [] });
    setSelectedManagedProject(null);
    setProjectCollaboratorCandidates([]);
    setInboxIssues([]);
    setAccounts([]);
    setCategories([]);
    setOperations(null);
    setBusinessGold(null);
    setBusinessGoldSources([]);
    setBusinessGoldSelected([]);
    setBusinessGoldBulk("");
    setBusinessGoldMessage("");
    setBusinessGoldEditing(null);
    setSearchResponse(null);
    setWritingResponse(null);
    setWritingInstruction("");
    setWritingDraftText("");
    setWritingDrafts({ latest: null, saved: [], saved_count: 0, max_saved: 5 });
    setWritingDraftMessage("");
    setWritingActiveDraftKind(null);
    setWritingLatestEditPending(false);
    setEvolutionDigest(null);
    setEvolutionArtifacts([]);
    setEvolutionBaselines([]);
    setSelectedEvolutionArtifact(null);
    setEvolutionRun(null);
    setEvolutionMessage("");
  }

  async function handleRefreshOperations() {
    if (!token) return;
    setError("");
    try {
      const operationState = await kbFetch<OperationsStatus>(
        "v1/operations/status",
        {},
        token,
      );
      setOperations(operationState);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "运行状态刷新失败");
    }
  }

  async function handleRunEvaluation() {
    if (!token) return;
    setEvaluationBusy(true);
    setError("");
    try {
      await kbFetch(
        "v1/evaluations/run",
        { method: "POST" },
        token,
      );
      setOperations(await kbFetch<OperationsStatus>("v1/operations/status", {}, token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "技术评测运行失败");
    } finally {
      setEvaluationBusy(false);
    }
  }

  async function handleRunConcurrency() {
    if (!token) return;
    setConcurrencyBusy(true);
    setError("");
    try {
      await kbFetch(
        "v1/evaluations/concurrency",
        { method: "POST" },
        token,
      );
      setOperations(await kbFetch<OperationsStatus>("v1/operations/status", {}, token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "5 人并发测试运行失败");
    } finally {
      setConcurrencyBusy(false);
    }
  }

  async function saveBusinessGoldDrafts(cases: Record<string, unknown>[]) {
    if (!token) return;
    const registry = await kbFetch<BusinessGoldRegistry>(
      "v1/evaluations/business-gold/import",
      {
        method: "POST",
        body: JSON.stringify({
          confirmation: "确认导入业务金标草稿",
          cases,
        }),
      },
      token,
    );
    setBusinessGold(registry);
    setBusinessGoldSelected([]);
  }

  async function handleCreateBusinessGold(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const formElement = event.currentTarget;
    const data = new FormData(formElement);
    const expectedType = String(data.get("expected_type") || "source");
    const sourceId = String(data.get("document_id") || "");
    const source = businessGoldSources.find((item) => item.document_id === sourceId);
    const page = Number(data.get("page") || 1);
    let expected: Record<string, unknown>;
    if (expectedType === "source") {
      if (!source) {
        setError("请选择一份正式来源资料");
        return;
      }
      if (!Number.isInteger(page) || page < 1 || page > Math.max(source.page_count, 1)) {
        setError(`页码必须在 1–${Math.max(source.page_count, 1)} 之间`);
        return;
      }
      expected = {
        document_id: source.document_id,
        page,
        reference_answer: String(data.get("reference_answer") || "").trim(),
        key_points: String(data.get("key_points") || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
        forbidden_claims: String(data.get("forbidden_claims") || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
      };
    } else if (expectedType === "refusal") {
      expected = { expect_refusal: true };
    } else {
      expected = { expect_no_leak: true };
    }
    setBusinessGoldBusy(true);
    setBusinessGoldMessage("");
    setError("");
    try {
      await saveBusinessGoldDrafts([{
        id: `business-${crypto.randomUUID()}`,
        category: String(data.get("category") || "business_fact").trim(),
        question: String(data.get("question") || "").trim(),
        scope: String(data.get("scope") || "auto"),
        retrieval: String(data.get("retrieval") || "exact"),
        actor: expectedType === "no_leak"
          ? { role: "employee", confidentiality_ceiling: "L1" }
          : { role: "founder", confidentiality_ceiling: "L5" },
        expected,
      }]);
      formElement.reset();
      setBusinessGoldMessage("已保存为待确认草稿；只有创始人单独批准后才会计入业务金标。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "业务金标草稿保存失败");
    } finally {
      setBusinessGoldBusy(false);
    }
  }

  async function handleImportBusinessGold() {
    if (!token) return;
    setBusinessGoldBusy(true);
    setBusinessGoldMessage("");
    setError("");
    try {
      const cases = parseBusinessGoldCases(businessGoldBulk);
      await saveBusinessGoldDrafts(cases);
      setBusinessGoldBulk("");
      setBusinessGoldMessage(`已导入 ${cases.length} 道待确认草稿；导入内容不会自动获批。`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "批量导入失败");
    } finally {
      setBusinessGoldBusy(false);
    }
  }

  async function handleGenerateBusinessGold() {
    if (!token) return;
    setBusinessGoldBusy(true);
    setBusinessGoldMessage("");
    setError("");
    try {
      const registry = await kbFetch<BusinessGoldRegistry>(
        "v1/evaluations/business-gold/generate",
        {
          method: "POST",
          body: JSON.stringify({
            target: 150,
            confirmation: "确认生成业务金标候选题",
          }),
        },
        token,
      );
      setBusinessGold(registry);
      const created = registry.generation?.created || 0;
      const shortfall = registry.generation?.shortfall || 0;
      setBusinessGoldMessage(
        shortfall
          ? `已生成 ${created} 道真实资料候选题，尚缺 ${shortfall} 道；系统没有用重复题或虚构资料补数。`
          : `已生成 ${created} 道真实资料候选题。请逐题核对标准答案、关键点和禁用说法后再批准。`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "候选题生成失败");
    } finally {
      setBusinessGoldBusy(false);
    }
  }

  async function handleEditBusinessGold(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!businessGoldEditing) return;
    const data = new FormData(event.currentTarget);
    setBusinessGoldBusy(true);
    setBusinessGoldMessage("");
    setError("");
    try {
      await saveBusinessGoldDrafts([{
        ...businessGoldEditing,
        question: String(data.get("question") || "").trim(),
        expected: {
          ...businessGoldEditing.expected,
          reference_answer: String(data.get("reference_answer") || "").trim(),
          key_points: String(data.get("key_points") || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
          forbidden_claims: String(data.get("forbidden_claims") || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
        },
      }]);
      setBusinessGoldEditing(null);
      setBusinessGoldMessage("题目和答案口径已保存为待确认草稿。修改后需要重新批准。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "业务金标修改失败");
    } finally {
      setBusinessGoldBusy(false);
    }
  }

  async function handleApproveBusinessGold(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !businessGoldSelected.length) return;
    const formElement = event.currentTarget;
    const data = new FormData(formElement);
    setBusinessGoldBusy(true);
    setBusinessGoldMessage("");
    setError("");
    try {
      const registry = await kbFetch<BusinessGoldRegistry>(
        "v1/evaluations/business-gold/approve",
        {
          method: "POST",
          body: JSON.stringify({
            case_ids: businessGoldSelected,
            confirmation: data.get("confirmation"),
            owner_note: data.get("owner_note"),
          }),
        },
        token,
      );
      setBusinessGold(registry);
      setBusinessGoldSelected([]);
      formElement.reset();
      setBusinessGoldMessage("所选题目已批准。运行一次评测后，验收状态会按已批准题目更新。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "业务金标批准失败");
    } finally {
      setBusinessGoldBusy(false);
    }
  }

  async function handleSearch(event?: FormEvent) {
    event?.preventDefault();
    if (!question.trim() || !token) return;
    setSearching(true);
    setSubmittedSearchQuery(question.trim());
    setError("");
    try {
      const response = await kbFetch<SearchResponse>(
        "v1/search",
        {
          method: "POST",
          body: JSON.stringify({ query: question.trim(), scope: "auto", limit: 20, offset: 0 }),
        },
        token,
      );
      setSearchResponse(response);
      scrollToMobileResult(searchResultRef);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "检索失败");
    } finally {
      setSearching(false);
    }
  }

  async function handleLoadMoreSearch() {
    if (!token || !searchResponse || !submittedSearchQuery || searchingMore) return;
    setSearchingMore(true);
    setError("");
    try {
      const response = await kbFetch<SearchResponse>(
        "v1/search",
        {
          method: "POST",
          body: JSON.stringify({
            query: submittedSearchQuery,
            scope: "auto",
            limit: 20,
            offset: searchResponse.results.length,
          }),
        },
        token,
      );
      setSearchResponse((current) => {
        if (!current) return response;
        const known = new Set(current.results.map((item) => item.document_id));
        return {
          ...current,
          total: response.total,
          limit: response.limit,
          results: [
            ...current.results,
            ...response.results.filter((item) => !known.has(item.document_id)),
          ],
        };
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "继续加载失败");
    } finally {
      setSearchingMore(false);
    }
  }

  async function handleWriting(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setWritingBusy(true);
    setError("");
    setWritingError("");
    const form = new FormData(event.currentTarget);
    const instruction = String(form.get("instruction") || "").trim();
    setWritingInstruction(instruction);
    try {
      const response = await kbFetch<WritingResponse>(
        "v1/writing/draft",
        {
          method: "POST",
          body: JSON.stringify({
            instruction,
            category: String(form.get("category") || "").trim() || null,
            scope: String(form.get("scope") || "all"),
            allow_l3_generation: form.get("allow_l3_generation") === "on",
          }),
        },
        token,
      );
      setWritingResponse(response);
      setWritingDraftText(response.draft);
      setWritingDraftView("preview");
      setWritingActiveDraftKind("latest");
      setWritingLatestEditPending(false);
      setWritingDraftMessage("最近一次创作已自动保存，刷新页面也不会丢失。");
      scrollToMobileResult(writingResultRef);
      await loadWritingDrafts();
    } catch (cause) {
      setWritingError(cause instanceof Error ? cause.message : "初稿生成失败");
    } finally {
      setWritingBusy(false);
    }
  }

  function restoreWritingDraft(record: WritingDraftRecord, message: string) {
    const savedResponse = record.response || null;
    setWritingInstruction(record.instruction || "");
    setWritingDraftText(record.draft);
    setWritingResponse(savedResponse && Array.isArray(savedResponse.sources) ? savedResponse : {
      draft: record.draft,
      sources: record.sources || [],
      generation_mode: record.generation_mode === "llm" || record.generation_mode === "local_evidence"
        ? record.generation_mode
        : "local_only",
      generation_model: record.generation_model || null,
      generation_degraded: false,
      retrieval_mode: "saved_draft",
      retrieval_degraded: false,
      effective_category: null,
      effective_category_name: null,
      category_auto_inferred: false,
      restricted_source_count: 0,
      l3_authorized_for_request: false,
      notice: "这是已恢复的创作草稿。",
    });
    setWritingDraftView("preview");
    setWritingActiveDraftKind(record.kind === "saved" ? "saved" : "latest");
    setWritingLatestEditPending(false);
    setWritingError("");
    setWritingDraftMessage(message);
  }

  async function loadWritingDrafts(restoreLatest = false) {
    if (!token) return;
    try {
      const registry = await kbFetch<WritingDraftRegistry>("v1/writing/drafts", {}, token);
      setWritingDrafts(registry);
      if (restoreLatest && registry.latest) {
        restoreWritingDraft(registry.latest, "已自动恢复最近一次创作，可继续编辑。未计入 5 条长期保存名额。");
      }
    } catch (cause) {
      setWritingError(cause instanceof Error ? cause.message : "创作记录加载失败");
    }
  }

  async function handleSaveWritingDraft() {
    if (!token || !writingDraftText.trim() || writingDrafts.saved_count >= writingDrafts.max_saved) return;
    setWritingDraftBusy("save");
    setWritingDraftMessage("");
    try {
      await kbFetch<WritingDraftRecord>(
        "v1/writing/drafts",
        {
          method: "POST",
          body: JSON.stringify({
            title: writingTitle(writingDraftText, writingInstruction),
            instruction: writingInstruction,
            draft: writingDraftText,
            category: writingResponse?.effective_category || null,
            scope: "all",
            generation_mode: writingResponse?.generation_mode || null,
            generation_model: writingResponse?.generation_model || null,
            sources: writingResponse?.sources || [],
            response: writingResponse ? { ...writingResponse, draft: writingDraftText } : null,
          }),
        },
        token,
      );
      await loadWritingDrafts();
      setWritingDraftMessage("已长期保存，可从下方记录随时恢复。");
    } catch (cause) {
      setWritingDraftMessage(cause instanceof Error ? cause.message : "草稿保存失败");
    } finally {
      setWritingDraftBusy("");
    }
  }

  async function handleDeleteWritingDraft(id: string) {
    if (!token) return;
    setWritingDraftBusy(`delete-${id}`);
    setWritingDraftMessage("");
    try {
      await kbFetch(`v1/writing/drafts/${encodeURIComponent(id)}`, { method: "DELETE" }, token);
      await loadWritingDrafts();
      setWritingDraftMessage("已删除这条长期保存记录。最近一次自动保存不受影响。");
    } catch (cause) {
      setWritingDraftMessage(cause instanceof Error ? cause.message : "草稿删除失败");
    } finally {
      setWritingDraftBusy("");
    }
  }

  function handleDownloadWritingDraft() {
    if (!writingDraftText.trim()) return;
    const sourceLines = (writingResponse?.sources || []).map((source, index) => (
      `${index + 1}. ${source.title}｜${source.version || "版本未确认"}｜第 ${source.page} 页`
    ));
    const generatedAt = new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
    const appendix = [
      "",
      "---",
      `生成/下载时间：${generatedAt}`,
      sourceLines.length ? "" : null,
      sourceLines.length ? "引用资料：" : null,
      ...sourceLines,
    ].filter((line): line is string => line !== null).join("\n");
    const blob = new Blob([`${writingDraftText.trim()}\n${appendix}\n`], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = safeWritingFilename(writingTitle(writingDraftText, writingInstruction));
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  async function handleEvolutionDigest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const form = new FormData(event.currentTarget);
    setEvolutionBusy(true);
    setError("");
    try {
      setEvolutionDigest(
        await kbFetch<EvolutionDigest>(
          "v1/evolution/digest",
          {
            method: "POST",
            body: JSON.stringify({
              artifact: form.get("artifact"),
              cutoff_date: form.get("cutoff_date"),
              reviewed_through: form.get("reviewed_through"),
              audience: form.get("audience"),
              limit: 30,
            }),
          },
          token,
        ),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "知识变化摘要生成失败");
    } finally {
      setEvolutionBusy(false);
    }
  }

  async function openEvolutionArtifact(artifactId: string) {
    if (!token) return;
    setEvolutionActionBusy(`open-${artifactId}`);
    setEvolutionMessage("");
    setError("");
    try {
      const artifact = await kbFetch<MaintainedArtifact>(
        `v1/evolution/artifacts/${artifactId}`,
        {},
        token,
      );
      setSelectedEvolutionArtifact(artifact);
      const latestRun = artifact.runs?.[0];
      setEvolutionRun(
        latestRun
          ? await kbFetch<EvolutionReviewRun>(
              `v1/evolution/runs/${latestRun.id}`,
              {},
              token,
            )
          : null,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "维护资料读取失败");
    } finally {
      setEvolutionActionBusy("");
    }
  }

  async function refreshEvolutionLists(activeToken = token) {
    if (!activeToken) return;
    const [artifacts, baselines] = await Promise.all([
      kbFetch<MaintainedArtifact[]>("v1/evolution/artifacts", {}, activeToken),
      kbFetch<EvolutionBaselineDocument[]>(
        "v1/evolution/baseline-documents?artifact_type=company_profile",
        {},
        activeToken,
      ),
    ]);
    setEvolutionArtifacts(artifacts);
    setEvolutionBaselines(baselines);
  }

  async function handleRegisterEvolutionArtifact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setEvolutionActionBusy("register");
    setEvolutionMessage("");
    setError("");
    try {
      const artifact = await kbFetch<MaintainedArtifact>(
        "v1/evolution/artifacts",
        {
          method: "POST",
          body: JSON.stringify({
            name: String(data.get("name") || "").trim(),
            artifact_type: "company_profile",
            current_document_id: data.get("current_document_id"),
            audience: data.get("audience"),
            cutoff_date: data.get("cutoff_date") || null,
            review_cadence_days: Number(data.get("review_cadence_days") || 90),
            section_map: {
              company_overview: "公司概况",
              milestones: "发展与活动",
              representative_cases: "代表案例",
              visual_assets: "图片素材",
            },
          }),
        },
        token,
      );
      await refreshEvolutionLists();
      await openEvolutionArtifact(artifact.id);
      setEvolutionMessage("维护资料已登记；系统只会生成待审候选，不会自动改稿或发布。");
      form.reset();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "维护资料登记失败");
    } finally {
      setEvolutionActionBusy("");
    }
  }

  async function handleStartEvolutionReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedEvolutionArtifact) return;
    const data = new FormData(event.currentTarget);
    setEvolutionActionBusy("start-review");
    setEvolutionMessage("");
    setError("");
    try {
      const run = await kbFetch<EvolutionReviewRun>(
        `v1/evolution/artifacts/${selectedEvolutionArtifact.id}/runs`,
        {
          method: "POST",
          body: JSON.stringify({
            reviewed_through: data.get("reviewed_through"),
            limit: 100,
          }),
        },
        token,
      );
      setEvolutionRun(run);
      await refreshEvolutionLists();
      setEvolutionMessage("本次变化候选已持久保存，等待逐项人工决策。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "定期复核启动失败");
    } finally {
      setEvolutionActionBusy("");
    }
  }

  async function handleEvolutionDecision(
    event: FormEvent<HTMLFormElement>,
    candidate: PersistedEvolutionCandidate,
  ) {
    event.preventDefault();
    if (!token || !evolutionRun) return;
    const data = new FormData(event.currentTarget);
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const decision: "approve" | "reject" = submitter?.value === "reject" ? "reject" : "approve";
    setEvolutionActionBusy(`candidate-${candidate.id}`);
    setEvolutionMessage("");
    setError("");
    try {
      await kbFetch(
        `v1/evolution/candidates/${candidate.id}/decision`,
        {
          method: "POST",
          body: JSON.stringify({
            decision,
            confirmation: String(data.get("confirmation") || "").trim(),
            note: String(data.get("note") || "").trim() || null,
          }),
        },
        token,
      );
      setEvolutionRun(
        await kbFetch<EvolutionReviewRun>(
          `v1/evolution/runs/${evolutionRun.id}`,
          {},
          token,
        ),
      );
      setEvolutionMessage(decision === "approve" ? "候选已纳入变更计划范围。" : "候选已标记为本次不纳入。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "候选决策失败");
    } finally {
      setEvolutionActionBusy("");
    }
  }

  async function handleEvolutionPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !evolutionRun) return;
    const data = new FormData(event.currentTarget);
    setEvolutionActionBusy("change-plan");
    setEvolutionMessage("");
    setError("");
    try {
      await kbFetch(
        `v1/evolution/runs/${evolutionRun.id}/change-plan`,
        {
          method: "POST",
          body: JSON.stringify({ confirmation: data.get("confirmation") }),
        },
        token,
      );
      setEvolutionRun(
        await kbFetch<EvolutionReviewRun>(
          `v1/evolution/runs/${evolutionRun.id}`,
          {},
          token,
        ),
      );
      setEvolutionMessage("逐项变更计划已生成；当前公司介绍仍未发生变化。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "变更计划生成失败");
    } finally {
      setEvolutionActionBusy("");
    }
  }

  async function handleCloseEvolutionReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !evolutionRun || !selectedEvolutionArtifact) return;
    const data = new FormData(event.currentTarget);
    setEvolutionActionBusy("close-review");
    setEvolutionMessage("");
    setError("");
    try {
      setEvolutionRun(
        await kbFetch<EvolutionReviewRun>(
          `v1/evolution/runs/${evolutionRun.id}/close`,
          {
            method: "POST",
            body: JSON.stringify({ confirmation: data.get("confirmation") }),
          },
          token,
        ),
      );
      await refreshEvolutionLists();
      const artifact = await kbFetch<MaintainedArtifact>(
        `v1/evolution/artifacts/${selectedEvolutionArtifact.id}`,
        {},
        token,
      );
      setSelectedEvolutionArtifact(artifact);
      setEvolutionMessage("本次复核已记录。资料截止日未改变，下一轮复核日期已更新。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "复核完成失败");
    } finally {
      setEvolutionActionBusy("");
    }
  }

  async function handleEvolutionBaselineUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedEvolutionArtifact) return;
    const data = new FormData(event.currentTarget);
    setEvolutionActionBusy("baseline");
    setEvolutionMessage("");
    setError("");
    try {
      const artifact = await kbFetch<MaintainedArtifact>(
        `v1/evolution/artifacts/${selectedEvolutionArtifact.id}/baseline`,
        {
          method: "POST",
          body: JSON.stringify({
            current_document_id: data.get("current_document_id"),
            cutoff_date: data.get("cutoff_date"),
            confirmation: data.get("confirmation"),
          }),
        },
        token,
      );
      setSelectedEvolutionArtifact(artifact);
      setEvolutionRun(null);
      await refreshEvolutionLists();
      setEvolutionMessage("维护资料基线已指向正式发布的新版本；历史版本仍完整保留。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "维护资料基线更新失败");
    } finally {
      setEvolutionActionBusy("");
    }
  }

  async function handlePreview(documentId: string, page = 1) {
    if (!token) return;
    const previewKey = `${documentId}-${page}`;
    const previewWindow = window.open("about:blank", "_blank");
    if (!previewWindow) {
      setError("浏览器阻止了预览窗口，请允许本站打开新窗口后重试。");
      return;
    }
    previewWindow.opener = null;
    previewWindow.document.title = "正在打开引用原页…";
    previewWindow.document.body.textContent = "正在安全读取引用原页…";
    setPreviewBusy(previewKey);
    setError("");
    try {
      const response = await fetch(
        `/api/kb/v1/documents/${documentId}/preview-ticket?page=${page}`,
        {
          method: "POST",
          headers: { authorization: `Bearer ${token}` },
          cache: "no-store",
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(apiErrorMessage(payload, response.status));
      }
      const payload = await response.json() as { path: string };
      previewWindow.location.replace(`/api/kb${payload.path}#page=${page}`);
    } catch (cause) {
      previewWindow.close();
      setError(cause instanceof Error ? cause.message : "预览失败");
    } finally {
      setPreviewBusy("");
    }
  }

  async function refreshReviewQueue() {
    if (!token) return;
    setReviewQueue(await kbFetch<ReviewItem[]>("v1/review/queue", {}, token));
  }

  async function handleConfirmReview(item: ReviewItem) {
    if (!token || !item.confirm_eligible) return;
    setReviewBusy(`confirm-${item.document_id}`);
    setReviewMessage("");
    setError("");
    try {
      const response = await kbFetch<{ notice: string }>(
        `v1/review/${item.document_id}/confirm`,
        { method: "POST" },
        token,
      );
      const [queue, service, projectRows] = await Promise.all([
        kbFetch<ReviewItem[]>("v1/review/queue", {}, token),
        kbFetch<Status>("v1/status", {}, token),
        kbFetch<Project[]>("v1/projects", {}, token),
      ]);
      setReviewQueue(queue);
      setSelectedReviewIds((current) => current.filter((id) => id !== item.document_id));
      setStatus(service);
      setProjects(projectRows);
      setReviewMessage(response.notice);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "确认入库失败");
    } finally {
      setReviewBusy("");
    }
  }

  async function handleRejectReview(item: ReviewItem) {
    if (!token || item.knowledge_status !== "candidate") return;
    if (!window.confirm(`确认拒绝《${item.title}》入库？\n\nNAS 原文件会保留，但不会进入智库检索。`)) return;
    setReviewBusy(`reject-${item.document_id}`);
    setReviewMessage("");
    setError("");
    try {
      const response = await kbFetch<{ notice: string }>(
        `v1/review/${item.document_id}/decline`,
        {
          method: "POST",
          body: JSON.stringify({ confirmation: "确认拒绝入库" }),
        },
        token,
      );
      const [queue, service, projectRows] = await Promise.all([
        kbFetch<ReviewItem[]>("v1/review/queue", {}, token),
        kbFetch<Status>("v1/status", {}, token),
        kbFetch<Project[]>("v1/projects", {}, token),
      ]);
      setReviewQueue(queue);
      setSelectedReviewIds((current) => current.filter((id) => id !== item.document_id));
      setStatus(service);
      setProjects(projectRows);
      setReviewMessage(response.notice);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "拒绝入库失败");
    } finally {
      setReviewBusy("");
    }
  }

  function uploadOneFile(
    file: File,
    index: number,
    total: number,
  ): Promise<UploadResult> {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", "/api/kb/v1/uploads");
      request.setRequestHeader("authorization", `Bearer ${token}`);
      request.timeout = 30 * 60 * 1000;
      request.upload.onprogress = (event) => {
        if (!event.lengthComputable) return;
        const fileProgress = event.loaded / event.total;
        setUploadProgress(Math.round(((index + fileProgress) / total) * 100));
      };
      request.onload = () => {
        let payload: UploadResult | { detail?: string } | null = null;
        try {
          payload = JSON.parse(request.responseText) as UploadResult | { detail?: string };
        } catch {
          // A non-JSON response is converted to a concise upload error below.
        }
        if (request.status >= 200 && request.status < 300) {
          resolve(payload as UploadResult);
        } else {
          const failure = new Error(
            (payload as { detail?: string } | null)?.detail || `上传失败（${request.status}）`,
          ) as UploadRequestError;
          failure.status = request.status;
          reject(failure);
        }
      };
      request.onerror = () => {
        const failure = new Error("网络中断，上传未完成") as UploadRequestError;
        failure.status = 0;
        reject(failure);
      };
      request.ontimeout = () => {
        const failure = new Error("上传超时，请检查网络后重试") as UploadRequestError;
        failure.status = 408;
        reject(failure);
      };
      const body = new FormData();
      body.set("file", file, file.name);
      body.set("department", uploadDepartment);
      body.set("confidentiality", uploadConfidentiality);
      if (uploadFolderName) {
        const relativeParts = file.webkitRelativePath.split("/");
        body.set("folder_name", uploadFolderName);
        body.set("relative_path", relativeParts.slice(1).join("/"));
      }
      request.send(body);
    });
  }

  async function uploadOneFileWithRetry(
    file: File,
    index: number,
    total: number,
  ): Promise<UploadResult> {
    const retryableStatuses = new Set([0, 404, 408, 425, 429, 500, 502, 503, 504]);
    const delays = [3_000, 6_000, 12_000];
    let lastFailure: unknown;
    for (let attempt = 0; attempt <= delays.length; attempt += 1) {
      try {
        return await uploadOneFile(file, index, total);
      } catch (cause) {
        lastFailure = cause;
        const status = (cause as UploadRequestError | null)?.status;
        if (attempt >= delays.length || !retryableStatuses.has(status ?? -1)) throw cause;
        await new Promise((resolve) => window.setTimeout(resolve, delays[attempt]));
      }
    }
    throw lastFailure;
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!token || !user || uploadFiles.length === 0) return;
    setUploadBusy(true);
    setUploadProgress(0);
    setUploadMessage("");
    setError("");
    let completed = 0;
    let duplicatesFiltered = 0;
    let pendingReview = 0;
    let automaticallyApproved = 0;
    let processing = 0;
    const failed: { file: File; message: string }[] = [];
    for (let index = 0; index < uploadFiles.length; index += 1) {
      try {
        const result = await uploadOneFileWithRetry(uploadFiles[index], index, uploadFiles.length);
        completed += 1;
        if (result.duplicate_filtered) duplicatesFiltered += 1;
        else if (!result.document_id) processing += 1;
        else if (result.review_required) pendingReview += 1;
        else automaticallyApproved += 1;
      } catch (cause) {
        failed.push({
          file: uploadFiles[index],
          message: cause instanceof Error ? cause.message : "上传失败",
        });
      }
    }
    setUploadProgress(100);
    if (failed.length === 0) {
      setUploadFiles([]);
      setUploadFolderName("");
      form.reset();
    } else {
      setUploadFiles(failed.map((item) => item.file));
      setError(
        `${completed} 份已完成；${failed.length} 份在自动重试后仍未完成，已保留在待上传列表。请稍后再次点击上传。` +
        ` 首个失败文件：${failed[0].file.name}（${failed[0].message}）`,
      );
    }
    setUploadMessage([
      `已上传 ${completed} 份资料`,
      pendingReview ? `${pendingReview} 份进入审核` : "",
      automaticallyApproved ? `${automaticallyApproved} 份素材已自动入库` : "",
      duplicatesFiltered ? `${duplicatesFiltered} 份完全重复资料已过滤` : "",
      processing ? `${processing} 份由后台继续解析` : "",
    ].filter(Boolean).join("；") + "。");
    try {
      const canReview = ["founder", "knowledge_admin", "department_owner"].includes(user.role);
      const [service, queue] = await Promise.all([
        kbFetch<Status>("v1/status", {}, token),
        canReview
          ? kbFetch<ReviewItem[]>("v1/review/queue", {}, token)
          : Promise.resolve([]),
      ]);
      setStatus(service);
      if (canReview) setReviewQueue(queue);
    } catch (cause) {
      if (failed.length === 0) {
        setError(`资料已上传，但刷新系统状态失败：${cause instanceof Error ? cause.message : "请稍后刷新页面"}`);
      }
    } finally {
      setUploadBusy(false);
    }
  }

  async function handleContractSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selected = contractCategories.find((item) => item.key === contractCategory);
    if (!token || !contractCategory || !contractQuery.trim() || !selected?.can_search) return;
    setContractBusy(true);
    setContractMessage("");
    setError("");
    try {
      const response = await kbFetch<SearchResponse>(
        "v1/contracts/search",
        {
          method: "POST",
          body: JSON.stringify({
            query: contractQuery.trim(),
            category: contractCategory,
            limit: 20,
          }),
        },
        token,
      );
      setContractSearchResponse(response);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "合同检索失败");
    } finally {
      setContractBusy(false);
    }
  }

  async function handleContractUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!token || !contractCategory || contractFiles.length === 0) return;
    const selectedCategory = contractCategories.find((item) => item.key === contractCategory);
    if (!selectedCategory?.can_upload) return;
    setContractBusy(true);
    setContractMessage("");
    setError("");
    let completed = 0;
    let duplicatesFiltered = 0;
    let automaticallyFiled = 0;
    const uploadFolder = contractSelectionMode === "folder" ? contractFolderName : "";
    setContractUploadProgress({ completed: 0, total: contractFiles.length });
    try {
      for (const file of contractFiles) {
        const body = new FormData();
        body.set("file", file, file.name);
        body.set("category", contractCategory);
        body.set("relative_path", file.webkitRelativePath || file.name);
        const response = await fetch("/api/kb/v1/contracts/uploads", {
          method: "POST",
          headers: { authorization: `Bearer ${token}` },
          body,
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(apiErrorMessage(payload, response.status));
        }
        const payload = await response.json() as {
          duplicate_filtered?: boolean;
          filing?: { mode?: string };
        };
        if (payload.duplicate_filtered) duplicatesFiltered += 1;
        if (payload.filing?.mode === "local_ai") automaticallyFiled += 1;
        completed += 1;
        setContractUploadProgress({ completed, total: contractFiles.length });
      }
      setContractFiles([]);
      setContractFolderName("");
      setContractPendingCount((current) => current + completed - duplicatesFiltered);
      form.reset();
      setContractMessage([
        uploadFolder
          ? `文件夹“${uploadFolder}”已在 NAS 对应合同分类下重建，${completed} 份合同传输完成`
          : `已上传 ${completed} 份合同原件`,
        completed - duplicatesFiltered > 0
          ? `${completed - duplicatesFiltered} 份已进入入库审核；审核通过后按原文件夹展示`
          : "",
        duplicatesFiltered ? `${duplicatesFiltered} 份完全重复资料已过滤` : "",
        automaticallyFiled ? `${automaticallyFiled} 份散件已由本地AI自动归档` : "",
      ].filter(Boolean).join("；") + "。");
      if (["founder", "knowledge_admin", "department_owner"].includes(user?.role || "")) {
        setReviewQueue(await kbFetch<ReviewItem[]>("v1/review/queue", {}, token));
      }
      const mine = await kbFetch<OwnedContractResponse>("v1/contracts/mine", {}, token);
      setOwnedContractDocuments(mine.items);
    } catch (cause) {
      setError(`${completed} 份已完成；${cause instanceof Error ? cause.message : "合同上传失败"}`);
    } finally {
      setContractBusy(false);
      setContractUploadProgress({ completed: 0, total: 0 });
    }
  }

  async function refreshContractFolders(category: string) {
    if (!token || !category) return;
    const response = await kbFetch<{ category: string; items: string[] }>(
      `v1/contracts/folders?category=${encodeURIComponent(category)}`,
      {},
      token,
    );
    setContractFolders((current) => ({ ...current, [category]: response.items }));
  }

  async function handleContractFolderCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !contractNewFolderCategory || !contractNewFolderPath.trim()) return;
    setContractManageBusy("create");
    setError("");
    try {
      await kbFetch(
        "v1/contracts/folders",
        {
          method: "POST",
          body: JSON.stringify({
            category: contractNewFolderCategory,
            folder_path: contractNewFolderPath.trim(),
          }),
        },
        token,
      );
      await refreshContractFolders(contractNewFolderCategory);
      setContractNewFolderPath("");
      setContractMessage("合同文件夹已创建，可立即将本人上传的合同移动进去。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "合同文件夹创建失败");
    } finally {
      setContractManageBusy("");
    }
  }

  async function handleContractMove(item: OwnedContractDocument) {
    if (!token) return;
    const targetCategory = contractMoveCategories[item.document_id] ?? item.category;
    const folderPath = contractMoveTargets[item.document_id] ?? item.folder_path ?? "";
    setContractManageBusy(item.document_id);
    setError("");
    setContractMoveErrors((current) => ({ ...current, [item.document_id]: "" }));
    try {
      const moved = await kbFetch<{
        category: ContractCategory["key"];
        category_name: string;
        confidentiality: string;
        folder_path: string;
      }>(
        `v1/contracts/${encodeURIComponent(item.document_id)}/folder`,
        {
          method: "PATCH",
          body: JSON.stringify({ target_category: targetCategory, folder_path: folderPath }),
        },
        token,
      );
      setContractMoveCategories((current) => ({
        ...current,
        [item.document_id]: moved.category,
      }));
      setContractMoveTargets((current) => ({
        ...current,
        [item.document_id]: moved.folder_path,
      }));
      const mine = await kbFetch<OwnedContractResponse>("v1/contracts/mine", {}, token);
      setOwnedContractDocuments(mine.items);
      await Promise.all([
        refreshContractFolders(item.category),
        item.category === moved.category ? Promise.resolve() : refreshContractFolders(moved.category),
      ]);
      if (
        (item.category === contractCategory || moved.category === contractCategory)
        && selectedContractCategory?.can_search
      ) {
        const archive = await kbFetch<ContractArchiveResponse>(
          `v1/contracts?category=${encodeURIComponent(contractCategory)}`,
          {},
          token,
        );
        setContractDocuments(archive.items);
      }
      setContractMessage(
        `《${item.title}》已移入${moved.category_name}（${confidentialityLabel(moved.confidentiality)}）${
          moved.folder_path ? `的“${moved.folder_path}”` : "分类根目录"
        }。`,
      );
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "合同移动失败";
      setContractMoveErrors((current) => ({
        ...current,
        [item.document_id]: message,
      }));
    } finally {
      setContractManageBusy("");
    }
  }

  async function refreshFinance() {
    if (!token || !selectedFinanceEntityId) return;
    const entity = financeEntities.find((item) => item.id === selectedFinanceEntityId);
    if (!entity) return;
    const query = `?entity_id=${encodeURIComponent(selectedFinanceEntityId)}&include_internal_transfers=${financeIncludeInternalTransfers ? "true" : "false"}`;
    const transferQuery = `?entity_id=${encodeURIComponent(selectedFinanceEntityId)}`;
    const [dashboard, batches, cash, transfers, annualYears, annualDashboard, purposeCorrections] = await Promise.all([
      kbFetch<FinanceDashboard>(`v1/finance/dashboard${query}`, {}, token),
      kbFetch<FinanceBatch[]>(`v1/finance/statements${query}`, {}, token),
      entity.show_cash
        ? kbFetch<CashLedgerEntry[]>(`v1/finance/cash${query}`, {}, token)
        : Promise.resolve([] as CashLedgerEntry[]),
      kbFetch<FinanceInternalTransferApiRegistry>(`v1/finance/internal-transfers${transferQuery}&review_status=all&limit=100`, {}, token),
      kbFetch<FinanceAnnualYears>(`v1/finance/annual-years${transferQuery}`, {}, token),
      financePeriodView === "realtime"
        ? Promise.resolve(null)
        : kbFetch<FinanceAnnualDashboard>(
            `v1/finance/annual${transferQuery}&year=${financePeriodView}&include_internal_transfers=${financeIncludeInternalTransfers ? "true" : "false"}`,
            {},
            token,
          ),
      kbFetch<FinancePurposeCorrectionRegistry>(`v1/finance/purpose-corrections${transferQuery}&review_status=all&limit=100`, {}, token),
    ]);
    setFinanceDashboard(dashboard);
    setFinanceBatches(batches);
    setFinanceCash(cash);
    setFinanceTransfers(normalizeFinanceTransferRegistry(transfers));
    setFinanceAnnualYears(annualYears.years);
    setFinancePurposeCorrections(purposeCorrections);
    if (annualDashboard) setFinanceAnnualDashboard(annualDashboard);
  }

  function handleFinanceEntitySelect(entityId: string) {
    setActive("财务分析");
    if (entityId === selectedFinanceEntityId) return;
    setSelectedFinanceEntityId(entityId);
    setFinancePeriodView("realtime");
    setFinanceAnnualYears([]);
    setFinanceAnnualDashboard(null);
    setFinanceDashboard(null);
    setFinanceBatches([]);
    setFinanceCash([]);
    setFinanceTransfers({ confirmed_amount: 0, candidate_amount: 0, confirmed_count: 0, candidate_count: 0, items: [] });
    setFinancePurposeCorrections({ items: [], pending_count: 0, approved_count: 0, rejected_count: 0 });
    setSelectedFinanceBatch("");
    setFinanceTransactions([]);
    setFinanceMessage("");
    setFinanceUploadError("");
  }

  async function handleFinanceTransferDecision(transferId: string, action: "confirm" | "reject" | "reset") {
    if (!token || !selectedFinanceEntityId) return;
    const prompt = action === "confirm"
      ? "确认将这笔流水标记为集团内部划转？确认后经营收支可按剔除口径统计。"
      : action === "reject"
        ? "确认这笔流水不是集团内部划转？排除后系统不会反复提示同一候选。"
        : "确认撤销这笔集团内部划转标记？撤销后系统会重新按规则识别。";
    if (!window.confirm(prompt)) return;
    setFinanceBusy(`transfer-${action}-${transferId}`);
    setFinanceMessage("");
    setError("");
    try {
      const transfer = financeTransfers.items.find((item) => item.id === transferId || item.transaction_id === transferId);
      await kbFetch(
        `v1/finance/internal-transfers/${encodeURIComponent(transferId)}?entity_id=${encodeURIComponent(selectedFinanceEntityId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            decision: action,
            target_entity_id: action === "confirm" ? transfer?.target_entity_id || null : null,
          }),
        },
        token,
      );
      setFinanceMessage(action === "confirm"
        ? "内部划转已经确认，经营口径已更新。"
        : action === "reject"
          ? "该流水已恢复为普通经营流水，系统不会再自动标记。"
          : "内部划转标记已经撤销并重新识别。");
      await refreshFinance();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "内部划转状态更新失败");
    } finally {
      setFinanceBusy("");
    }
  }

  async function handleFinanceReceivablePayableCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedFinanceEntityId) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setFinanceBusy("receivable-payable-create");
    setFinanceMessage("");
    setError("");
    try {
      await kbFetch("v1/finance/receivables-payables", {
        method: "POST",
        body: JSON.stringify({
          entity_id: selectedFinanceEntityId,
          direction: data.get("direction"),
          due_date: data.get("due_date"),
          amount: data.get("amount"),
          actual_amount: data.get("actual_amount") || 0,
          counterparty: String(data.get("counterparty") || "").trim() || null,
          note: String(data.get("note") || "").trim() || null,
        }),
      }, token);
      form.reset();
      setFinanceMessage("非项目应收应付已添加到财务总览。");
      await refreshFinance();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "应收应付添加失败");
    } finally {
      setFinanceBusy("");
    }
  }

  async function handleFinanceReceivablePayableUpdate(
    event: FormEvent<HTMLFormElement>,
    itemId: string,
  ) {
    event.preventDefault();
    if (!token || !selectedFinanceEntityId) return;
    const data = new FormData(event.currentTarget);
    setFinanceBusy(`receivable-payable-${itemId}`);
    setFinanceMessage("");
    setError("");
    try {
      await kbFetch(
        `v1/finance/receivables-payables/${encodeURIComponent(itemId)}?entity_id=${encodeURIComponent(selectedFinanceEntityId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            direction: data.get("direction"),
            due_date: data.get("due_date"),
            amount: data.get("amount"),
            actual_amount: data.get("actual_amount") || 0,
            counterparty: String(data.get("counterparty") || "").trim() || null,
            note: String(data.get("note") || "").trim() || null,
          }),
        },
        token,
      );
      setFinanceMessage("非项目应收应付记录已更新。");
      await refreshFinance();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "应收应付修改失败");
    } finally {
      setFinanceBusy("");
    }
  }

  async function handleStatementUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const form = event.currentTarget;
    const body = new FormData(form);
    if (!selectedFinanceEntityId) {
      setError("请先选择公司主体");
      return;
    }
    body.set("entity_id", selectedFinanceEntityId);
    body.delete("company_name");
    setFinanceBusy("upload");
    setFinanceMessage("");
    setFinanceUploadError("");
    setError("");
    try {
      const result = await kbFormFetch<FinanceBatch & { duplicate_file: boolean }>(
        "v1/finance/statements/upload",
        body,
        token,
      );
      setFinanceMessage(result.duplicate_file
        ? "该银行流水文件已导入，系统未重复写入。"
        : `已解析 ${result.row_count} 条流水，过滤 ${result.duplicate_count} 条重复记录，请核对后确认。`);
      form.reset();
      await refreshFinance();
      await handleFinanceBatchSelect(result.id);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "银行流水上传失败";
      setFinanceUploadError(message);
      setError(message);
    } finally {
      setFinanceBusy("");
    }
  }

  async function handleFinanceBatchSelect(batchId: string) {
    if (!token || !selectedFinanceEntityId) return;
    setSelectedFinanceBatch(batchId);
    setFinanceBusy(`batch-${batchId}`);
    setError("");
    try {
      setFinanceTransactions(await kbFetch<FinanceTransaction[]>(
        `v1/finance/statements/${batchId}/transactions?entity_id=${encodeURIComponent(selectedFinanceEntityId)}`,
        {},
        token,
      ));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "流水明细加载失败");
    } finally {
      setFinanceBusy("");
    }
  }

  async function handleTransactionUpdate(
    event: FormEvent<HTMLFormElement>,
    transactionId: string,
  ) {
    event.preventDefault();
    if (!token) return;
    const data = new FormData(event.currentTarget);
    const annotationOnly = String(data.get("annotation_only") || "") === "true";
    setFinanceBusy(`transaction-${transactionId}`);
    setError("");
    try {
      const payload: Record<string, string | null> = {
        category: String(data.get("category") || "其他"),
        project_reference: String(data.get("project_reference") || "").trim() || null,
        pm_project_id: String(data.get("pm_project_id") || "") || null,
      };
      if (!annotationOnly) {
        payload.transacted_at = String(data.get("transacted_at") || "") || null;
        payload.counterparty = String(data.get("counterparty") || "") || null;
      }
      await kbFetch(`v1/finance/transactions/${transactionId}?entity_id=${encodeURIComponent(selectedFinanceEntityId)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }, token);
      if (selectedFinanceBatch) await handleFinanceBatchSelect(selectedFinanceBatch);
      setFinanceMessage(annotationOnly
        ? "财务分类和项目关联已更新；银行原始附言及已采用用途未改动。"
        : "流水基础信息与业务核对信息已更新。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "流水修改失败");
    } finally {
      setFinanceBusy("");
    }
  }

  async function handlePurposeCorrectionRequest(
    event: FormEvent<HTMLFormElement>,
    transactionId: string,
  ) {
    event.preventDefault();
    if (!token || !selectedFinanceEntityId) return;
    const data = new FormData(event.currentTarget);
    const proposedPurpose = String(data.get("proposed_purpose") || "").trim();
    if (!proposedPurpose) {
      setError("请填写修正后的实际业务用途");
      return;
    }
    setFinanceBusy(`purpose-request-${transactionId}`);
    setFinanceMessage("");
    setError("");
    try {
      await kbFetch(
        `v1/finance/transactions/${encodeURIComponent(transactionId)}/purpose-corrections?entity_id=${encodeURIComponent(selectedFinanceEntityId)}`,
        {
          method: "POST",
          body: JSON.stringify({ proposed_purpose: proposedPurpose }),
        },
        token,
      );
      setFinanceMessage("用途修正已提交，创始人复核通过后才会正式生效。");
      await refreshFinance();
      if (selectedFinanceBatch) await handleFinanceBatchSelect(selectedFinanceBatch);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "用途修正提交失败");
    } finally {
      setFinanceBusy("");
    }
  }

  async function handlePurposeCorrectionReview(
    correctionId: string,
    decision: "approve" | "reject",
  ) {
    if (!token || !selectedFinanceEntityId) return;
    const reviewComment = window.prompt(
      decision === "approve"
        ? "确认批准这项用途修正？可填写复核说明（可留空）。"
        : "请填写拒绝原因（必填）。",
      "",
    );
    if (reviewComment === null) return;
    if (decision === "reject" && !reviewComment.trim()) {
      setError("拒绝用途修正时必须填写原因");
      return;
    }
    setFinanceBusy(`purpose-review-${correctionId}`);
    setFinanceMessage("");
    setError("");
    try {
      await kbFetch(
        `v1/finance/purpose-corrections/${encodeURIComponent(correctionId)}/review?entity_id=${encodeURIComponent(selectedFinanceEntityId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            decision,
            review_comment: reviewComment.trim() || null,
          }),
        },
        token,
      );
      setFinanceMessage(decision === "approve"
        ? "用途修正已通过，系统已采用复核后的实际业务用途。"
        : "用途修正已拒绝，系统继续保留原用途。");
      await refreshFinance();
      if (selectedFinanceBatch) await handleFinanceBatchSelect(selectedFinanceBatch);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "用途修正复核失败");
    } finally {
      setFinanceBusy("");
    }
  }

  async function handleConfirmStatement(batchId: string) {
    if (!token || !window.confirm("确认该批流水已经核对无误？确认后不能直接修改。")) return;
    setFinanceBusy(`confirm-${batchId}`);
    setError("");
    try {
      await kbFetch(`v1/finance/statements/${batchId}/confirm?entity_id=${encodeURIComponent(selectedFinanceEntityId)}`, { method: "POST" }, token);
      setFinanceMessage("该批银行流水已确认并进入财务分析。");
      await refreshFinance();
      await handleFinanceBatchSelect(batchId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "流水确认失败");
    } finally {
      setFinanceBusy("");
    }
  }

  async function handleDeleteStatement(batch: FinanceBatch) {
    if (!token || !selectedFinanceEntityId) return;
    const confirmed = batch.status === "confirmed";
    const prompt = confirmed
      ? `确认永久删除已确认批次“${batch.filename}”？这会删除 ${batch.row_count} 条流水，并同步从财务分析及项目收支中移除。此操作不可撤销。`
      : `确认永久删除待确认批次“${batch.filename}”？原始文件及 ${batch.row_count} 条解析记录都会删除。此操作不可撤销。`;
    if (!window.confirm(prompt)) return;
    setFinanceBusy(`delete-${batch.id}`);
    setFinanceMessage("");
    setError("");
    try {
      await kbFetch(
        `v1/finance/statements/${encodeURIComponent(batch.id)}?entity_id=${encodeURIComponent(selectedFinanceEntityId)}`,
        { method: "DELETE" },
        token,
      );
      if (selectedFinanceBatch === batch.id) {
        setSelectedFinanceBatch("");
        setFinanceTransactions([]);
      }
      setFinanceMessage(confirmed
        ? "已确认流水批次已由创始人永久删除，财务分析和项目收支已同步更新。"
        : "待确认流水批次及原始文件已永久删除。");
      await refreshFinance();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "流水批次删除失败");
    } finally {
      setFinanceBusy("");
    }
  }

  async function handleCashEntry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedFinanceEntityId) return;
    const entity = financeEntities.find((item) => item.id === selectedFinanceEntityId);
    if (!entity?.show_cash) {
      setError("账外现金仅在京奥电竞总公司账套中登记");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    setFinanceBusy("cash");
    setError("");
    try {
      await kbFetch("v1/finance/cash", {
        method: "POST",
        body: JSON.stringify({
          entity_id: entity.id,
          company_name: entity.name,
          cash_account: data.get("cash_account") || "公司现金",
          transaction_date: data.get("transaction_date"),
          direction: data.get("direction"),
          amount: data.get("amount"),
          category: data.get("category") || "其他",
          note: data.get("note"),
          pm_project_id: data.get("pm_project_id") || null,
        }),
      }, token);
      form.reset();
      setFinanceMessage("账外现金记录已登记。所有操作已写入审计日志。");
      await refreshFinance();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "现金记录登记失败");
    } finally {
      setFinanceBusy("");
    }
  }

  async function refreshManagedProjects(preferredId?: string) {
    if (!token) return;
    const registry = await kbFetch<ManagedProjectRegistry>("v1/pm/projects", {}, token);
    setManagedProjects(registry);
    const targetId = preferredId || selectedManagedProject?.id;
    if (targetId && registry.items.some((item) => item.id === targetId)) {
      setSelectedManagedProject(await kbFetch<ManagedProject>(`v1/pm/projects/${targetId}`, {}, token));
    } else if (targetId) {
      setSelectedManagedProject(null);
    }
  }

  async function handleManagedProjectSelect(projectId: string) {
    if (!token) return;
    setProjectBusy(`project-${projectId}`);
    setError("");
    try {
      setSelectedManagedProject(await kbFetch<ManagedProject>(`v1/pm/projects/${projectId}`, {}, token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "项目详情加载失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleCreateManagedProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const form = event.currentTarget;
    const body = new FormData(form);
    body.set("members_json", JSON.stringify(
      String(body.get("members") || "").split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean),
    ));
    body.delete("members");
    setProjectBusy("create");
    setError("");
    try {
      const project = await kbFormFetch<ManagedProject>("v1/pm/projects", body, token);
      form.reset();
      setProjectMessage(`项目 ${project.project_no} 已建立为草稿。`);
      await refreshManagedProjects(project.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "项目创建失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleUpdateManagedProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedManagedProject) return;
    const data = new FormData(event.currentTarget);
    setProjectBusy("project-update");
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${selectedManagedProject.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          project_no: data.get("project_no"),
          name: data.get("name"),
          company_name: data.get("company_name"),
          client: data.get("client"),
          client_contact: data.get("client_contact"),
          business_category: data.get("business_category"),
          members: String(data.get("members") || "").split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean),
          planned_start: data.get("planned_start"),
          planned_end: data.get("planned_end"),
          objective: data.get("objective"),
          contract_document_id: data.get("contract_document_id") || null,
          contract_status: data.get("contract_status") || "unsigned",
          contract_amount: data.get("contract_amount") || 0,
          budget_revenue: data.get("budget_revenue") || 0,
          budget_cost: data.get("budget_cost") || 0,
          budget_tax: data.get("budget_tax") || 0,
        }),
      }, token);
      setProjectMessage("项目基础信息和预算已更新。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "项目修改失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleProjectCollaborators(usernames: string[]) {
    if (!token || !selectedManagedProject) return;
    setProjectBusy("collaborators");
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${selectedManagedProject.id}/collaborators`, {
        method: "PUT",
        body: JSON.stringify({ usernames }),
      }, token);
      setProjectMessage("项目协作编辑权限已更新，并写入审计日志。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "协作成员权限更新失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleUpdateProjectContractStatus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedManagedProject) return;
    const data = new FormData(event.currentTarget);
    const contractStatus = data.get("contract_status") === "signed_received" ? "signed_received" : "unsigned";
    setProjectBusy("contract-status");
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${selectedManagedProject.id}/contract-status`, {
        method: "PATCH",
        body: JSON.stringify({ contract_status: contractStatus }),
      }, token);
      setProjectMessage(contractStatus === "signed_received" ? "合同状态已更新为已签署收件。" : "合同状态已更新为未签署。项目启动后将触发异常预警。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "合同状态更新失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleProjectProcessFinance(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedManagedProject) return;
    const data = new FormData(event.currentTarget);
    setProjectBusy("process-finance");
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${selectedManagedProject.id}/process-finance`, {
        method: "PATCH",
        body: JSON.stringify({
          process_received: data.get("process_received") || 0,
          process_spent: data.get("process_spent") || 0,
          process_advanced: data.get("process_advanced") || 0,
        }),
      }, token);
      setProjectMessage("项目过程资金已更新。三项数据为项目经理累计填报口径。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "项目过程资金更新失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleRequestProjectDeletion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedManagedProject) return;
    const data = new FormData(event.currentTarget);
    if (!window.confirm("提交后项目不会立即删除，将等待叶靖波复核。确认提交？")) return;
    setProjectBusy("deletion-request");
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${selectedManagedProject.id}/deletion-request`, {
        method: "POST",
        body: JSON.stringify({ reason: data.get("reason") }),
      }, token);
      setProjectMessage("删除申请已提交，等待叶靖波复核。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除申请提交失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleProjectDeletionDecision(
    event: FormEvent<HTMLFormElement>,
    requestId: string,
  ) {
    event.preventDefault();
    if (!token) return;
    const data = new FormData(event.currentTarget);
    const decision = String(data.get("decision") || "rejected");
    if (!window.confirm(decision === "approved" ? "批准后项目将从列表隐藏，确认删除？" : "确认驳回删除申请？")) return;
    setProjectBusy("deletion-decision");
    setError("");
    try {
      await kbFetch(`v1/pm/deletion-requests/${requestId}/decide`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          note: data.get("note") || null,
          deletion_password: data.get("deletion_password") || null,
        }),
      }, token);
      setProjectMessage(decision === "approved" ? "项目删除申请已批准。" : "项目删除申请已驳回。");
      await refreshManagedProjects();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除复核失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleConfigureProjectDeletePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const newPassword = String(data.get("new_password") || "");
    const confirmation = String(data.get("confirm_password") || "");
    if (newPassword !== confirmation) {
      setError("两次输入的项目删除密码不一致");
      return;
    }
    setProjectBusy("delete-password");
    setError("");
    try {
      const response = await kbFetch<FounderDeletePasswordStatus>(
        "v1/pm/founder-delete-password",
        {
          method: "PATCH",
          body: JSON.stringify({
            current_login_password: data.get("current_login_password"),
            new_password: newPassword,
          }),
        },
        token,
      );
      setProjectDeletePasswordConfigured(response.configured);
      setProjectMessage(response.status === "updated" ? "项目删除密码已修改。" : "项目删除密码已设置。");
      form.reset();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "项目删除密码设置失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleFounderProjectDelete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedManagedProject) return;
    const project = selectedManagedProject;
    const form = event.currentTarget;
    const data = new FormData(form);
    if (!window.confirm(`确认删除项目“${project.name}”？\n\n项目会从项目组合隐藏，但项目代码、附件、财务关联和审计记录都会保留。`)) return;
    setProjectBusy("founder-delete");
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${project.id}/founder-delete`, {
        method: "POST",
        body: JSON.stringify({
          deletion_password: data.get("deletion_password"),
          reason: data.get("reason"),
        }),
      }, token);
      form.reset();
      setProjectMessage(`项目 ${project.project_no} 已执行软删除；原始记录与审计链完整保留。`);
      await refreshManagedProjects(project.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "项目删除失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleProjectArchive(action: "archive" | "restore") {
    if (!token || !selectedManagedProject) return;
    const prompt = action === "archive"
      ? "归档后项目会移入归档区，但所有项目、资金和审计记录都会保留。确认归档？"
      : "确认将该项目恢复到已结案项目中？";
    if (!window.confirm(prompt)) return;
    setProjectBusy("project-archive");
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${selectedManagedProject.id}/archive`, {
        method: "POST",
        body: JSON.stringify({ action }),
      }, token);
      setProjectMessage(action === "archive" ? "项目已归档。" : "项目已恢复到已结案项目。 ");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "项目归档操作失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleProjectCashflow(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedManagedProject) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setProjectBusy("cashflow");
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${selectedManagedProject.id}/cashflow`, {
        method: "POST",
        body: JSON.stringify({
          direction: data.get("direction"),
          due_date: data.get("due_date"),
          amount: data.get("amount"),
          counterparty: data.get("counterparty") || null,
          note: data.get("note") || null,
        }),
      }, token);
      form.reset();
      setProjectMessage("收付款计划已添加。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "收付款计划添加失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleProjectCashflowActual(
    event: FormEvent<HTMLFormElement>,
    cashflowId: string,
  ) {
    event.preventDefault();
    if (!token || !selectedManagedProject) return;
    const data = new FormData(event.currentTarget);
    setProjectBusy(`actual-${cashflowId}`);
    setError("");
    try {
      await kbFetch(`v1/pm/cashflow/${cashflowId}/actual`, {
        method: "PATCH",
        body: JSON.stringify({
          actual_amount: data.get("actual_amount"),
          actual_date: data.get("actual_date") || null,
        }),
      }, token);
      setProjectMessage("财务实收/实付已经复核记录。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "实际收付款更新失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleSubmitInitiation() {
    if (!token || !selectedManagedProject || !window.confirm("提交后将由叶靖波复核，确认提交立项？")) return;
    setProjectBusy("submit-initiation");
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${selectedManagedProject.id}/submit-initiation`, { method: "POST" }, token);
      setProjectMessage("项目已提交立项复核。叶靖波通过后自动进入执行中。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "立项提交失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleProjectProgress(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedManagedProject) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setProjectBusy("progress");
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${selectedManagedProject.id}/progress`, {
        method: "POST",
        body: JSON.stringify({
          progress_percent: Number(data.get("progress_percent")),
          current_stage: data.get("current_stage"),
          completed: data.get("completed"),
          next_step: data.get("next_step"),
          risks: data.get("risks") || null,
          needs_coordination: data.get("needs_coordination") === "on",
        }),
      }, token);
      form.reset();
      setProjectMessage("项目进度已更新。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "进度更新失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleSubmitClosing(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedManagedProject) return;
    const form = event.currentTarget;
    const body = new FormData(form);
    setProjectBusy("closing");
    setError("");
    try {
      await kbFormFetch<ManagedProject>(
        `v1/pm/projects/${selectedManagedProject.id}/submit-closing`,
        body,
        token,
      );
      setProjectMessage("结案已提交叶靖波复核，通过后自动归档。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "结案提交失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleProjectReview(
    event: FormEvent<HTMLFormElement>,
    stage: "initiation" | "closing",
  ) {
    event.preventDefault();
    if (!token || !selectedManagedProject) return;
    const data = new FormData(event.currentTarget);
    const decision = String(data.get("decision") || "approved");
    if (!window.confirm(decision === "approved" ? "确认通过本轮复核？" : "确认退回给业务负责人修改？")) return;
    setProjectBusy(`review-${stage}`);
    setError("");
    try {
      await kbFetch(`v1/pm/projects/${selectedManagedProject.id}/review`, {
        method: "POST",
        body: JSON.stringify({
          stage,
          decision,
          note: data.get("note") || null,
        }),
      }, token);
      setProjectMessage(decision === "approved" ? "本账号已通过复核。" : "项目已退回业务负责人修改。");
      await refreshManagedProjects(selectedManagedProject.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "项目复核失败");
    } finally {
      setProjectBusy("");
    }
  }

  async function handleBatchConfirm() {
    if (!token) return;
    const eligibleIds = new Set(
      reviewQueue
        .filter((item) => (
          item.confirm_eligible
          && item.knowledge_status === "candidate"
          && ["L1", "L2", "L3"].includes(item.confidentiality)
        ))
        .map((item) => item.document_id),
    );
    const requestedIds = selectedReviewIds.filter((id) => eligibleIds.has(id));
    if (requestedIds.length === 0) return;
    const failedDetails: { document_id: string; detail: string }[] = [];
    let requestError = "";
    setReviewBusy("batch-confirm");
    setReviewMessage("");
    setError("");
    try {
      for (let offset = 0; offset < requestedIds.length; offset += BATCH_REVIEW_CHUNK_SIZE) {
        const documentIds = requestedIds.slice(offset, offset + BATCH_REVIEW_CHUNK_SIZE);
        try {
          const response = await kbFetch<{
            confirmed_count: number;
            failed_count: number;
            failed: { document_id: string; detail: string }[];
            notice: string;
          }>(
            "v1/review/confirm-batch",
            {
              method: "POST",
              body: JSON.stringify({ document_ids: documentIds }),
            },
            token,
          );
          failedDetails.push(...response.failed);
        } catch (cause) {
          requestError = cause instanceof Error ? cause.message : "批量确认失败";
          break;
        }
      }
      const [queue, service, projectRows] = await Promise.all([
        kbFetch<ReviewItem[]>("v1/review/queue", {}, token),
        kbFetch<Status>("v1/status", {}, token),
        kbFetch<Project[]>("v1/projects", {}, token),
      ]);
      setReviewQueue(queue);
      setStatus(service);
      setProjects(projectRows);
      const remainingIds = requestedIds.filter((documentId) => queue.some((item) => (
        item.document_id === documentId && item.knowledge_status === "candidate"
      )));
      const confirmedCount = requestedIds.length - remainingIds.length;
      setSelectedReviewIds(remainingIds);
      if (confirmedCount > 0) {
        setReviewMessage(
          remainingIds.length
            ? `已批量确认 ${confirmedCount} 份资料，剩余 ${remainingIds.length} 份仍待处理。`
            : `已批量确认 ${confirmedCount} 份资料。`,
        );
      }
      if (requestError) {
        setError(
          confirmedCount > 0
            ? `${requestError}；已成功确认 ${confirmedCount} 份，剩余资料仍保持勾选。`
            : requestError,
        );
      } else if (failedDetails.length > 0) {
        setError(`${failedDetails.length} 份资料未能确认：${failedDetails[0].detail}`);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "批量确认失败");
    } finally {
      setReviewBusy("");
    }
  }

  async function handleBatchReject() {
    if (!token || selectedReviewIds.length === 0) return;
    const candidateIds = new Set(
      reviewQueue
        .filter((item) => (
          item.knowledge_status === "candidate"
          && ["L1", "L2", "L3"].includes(item.confidentiality)
        ))
        .map((item) => item.document_id),
    );
    const requestedIds = selectedReviewIds.filter((id) => candidateIds.has(id));
    if (requestedIds.length === 0) return;
    if (!window.confirm(`确认拒绝所选 ${requestedIds.length} 份资料入库？\n\nNAS 原文件会保留，但不会进入智库检索。`)) return;
    const failedDetails: { document_id: string; detail: string }[] = [];
    let requestError = "";
    setReviewBusy("batch-reject");
    setReviewMessage("");
    setError("");
    try {
      for (let offset = 0; offset < requestedIds.length; offset += BATCH_REVIEW_CHUNK_SIZE) {
        const documentIds = requestedIds.slice(offset, offset + BATCH_REVIEW_CHUNK_SIZE);
        try {
          const response = await kbFetch<{
            rejected_count: number;
            failed_count: number;
            failed: { document_id: string; detail: string }[];
          }>(
            "v1/review/reject-batch",
            {
              method: "POST",
              body: JSON.stringify({
                document_ids: documentIds,
                confirmation: "确认拒绝入库",
              }),
            },
            token,
          );
          failedDetails.push(...response.failed);
        } catch (cause) {
          requestError = cause instanceof Error ? cause.message : "批量拒绝失败";
          break;
        }
      }
      const [queue, service, projectRows] = await Promise.all([
        kbFetch<ReviewItem[]>("v1/review/queue", {}, token),
        kbFetch<Status>("v1/status", {}, token),
        kbFetch<Project[]>("v1/projects", {}, token),
      ]);
      setReviewQueue(queue);
      setStatus(service);
      setProjects(projectRows);
      const remainingIds = requestedIds.filter((documentId) => queue.some((item) => (
        item.document_id === documentId && item.knowledge_status === "candidate"
      )));
      const rejectedCount = requestedIds.length - remainingIds.length;
      setSelectedReviewIds(remainingIds);
      if (rejectedCount > 0) {
        setReviewMessage(`已拒绝 ${rejectedCount} 份资料；NAS 原文件均保留。`);
      }
      if (requestError) {
        setError(
          rejectedCount > 0
            ? `${requestError}；已成功拒绝 ${rejectedCount} 份，剩余资料仍保持勾选。`
            : requestError,
        );
      } else if (failedDetails.length > 0) {
        setError(`${failedDetails.length} 份资料未能拒绝：${failedDetails[0].detail}`);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "批量拒绝失败");
    } finally {
      setReviewBusy("");
    }
  }

  async function handleScanInbox() {
    if (!token) return;
    setInboxScanBusy(true);
    setReviewMessage("");
    setError("");
    try {
      const response = await kbFetch<{
        status: string;
        counts: Record<string, number>;
      }>(
        "v1/review/inbox/scan",
        { method: "POST" },
        token,
      );
      const [queue, issueRows, operationState] = await Promise.all([
        kbFetch<ReviewItem[]>("v1/review/queue", {}, token),
        user?.role === "founder"
          ? kbFetch<InboxIssue[]>("v1/review/inbox/issues", {}, token)
          : Promise.resolve([]),
        kbFetch<OperationsStatus>("v1/operations/status", {}, token),
      ]);
      setReviewQueue(queue);
      setInboxIssues(issueRows);
      setOperations(operationState);
      setReviewMessage(
        `扫描完成：新增 ${response.counts.ingested || 0}，重复 ${response.counts.unchanged || 0}，等待稳定 ${response.counts.deferred || 0}，需处理 ${(response.counts.failed || 0) + (response.counts.unsupported || 0)}。`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "待审核目录扫描失败");
    } finally {
      setInboxScanBusy(false);
    }
  }

  async function handleIgnoreInboxIssue(issue: InboxIssue) {
    if (!token || inboxIssueBusy) return;
    setInboxIssueBusy(issue.id);
    setError("");
    setReviewMessage("");
    try {
      const response = await kbFetch<{ notice: string }>(
        `v1/review/inbox/issues/${issue.id}/ignore`,
        { method: "POST" },
        token,
      );
      const rows = await kbFetch<InboxIssue[]>(
        "v1/review/inbox/issues",
        {},
        token,
      );
      setInboxIssues(rows);
      setReviewMessage(response.notice);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "目录问题处理失败");
    } finally {
      setInboxIssueBusy("");
    }
  }

  async function refreshGovernance(offset = 0) {
    if (!token) return;
    const params = new URLSearchParams({ offset: String(offset), limit: "50" });
    if (governanceQuery.trim()) params.set("q", governanceQuery.trim());
    if (governanceDomain) params.set("domain", governanceDomain);
    if (governanceLevel) params.set("confidentiality", governanceLevel);
    if (governanceRole) params.set("role", governanceRole);
    if (governanceManualOnly) params.set("manual_only", "true");
    const rows = await kbFetch<GovernanceResponse>(
      `v1/governance/documents?${params.toString()}`,
      {},
      token,
    );
    setGovernance(rows);
    setGovernanceSelected([]);
  }

  async function handleGovernanceFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setGovernanceBusy("filter");
    setGovernanceMessage("");
    setError("");
    try {
      await refreshGovernance(0);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "资料治理列表刷新失败");
    } finally {
      setGovernanceBusy("");
    }
  }

  async function handleGovernanceBatch() {
    if (!token || governanceSelected.length === 0) return;
    if (["L4", "L5"].includes(governanceTarget) && governanceSelected.length !== 1) {
      setError("L4/L5高敏资料必须逐份确认，不能批量调整。");
      return;
    }
    if (governanceReason.trim().length < 4) {
      setError("请填写至少4个字的调整原因。");
      return;
    }
    setGovernanceBusy("batch");
    setGovernanceMessage("");
    setError("");
    try {
      const response = await kbFetch<{ notice: string }>(
        "v1/governance/documents/confidentiality",
        {
          method: "POST",
          body: JSON.stringify({
            document_ids: governanceSelected,
            confidentiality: governanceTarget,
            reason: governanceReason.trim(),
            confirmation: "确认调整资料密级",
          }),
        },
        token,
      );
      setGovernanceMessage(response.notice);
      await refreshGovernance(governance?.offset || 0);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "资料密级调整失败");
    } finally {
      setGovernanceBusy("");
    }
  }

  async function handleGovernanceAI(dryRun: boolean) {
    if (!token || user?.role !== "founder") return;
    if (!dryRun && !window.confirm("确认应用AI建议？L1至L3会先行调整，合同、L4/L5和低置信度资料仍保留人工确认。")) {
      return;
    }
    setGovernanceBusy(dryRun ? "ai-preview" : "ai-apply");
    setGovernanceMessage("");
    setError("");
    try {
      const report = await kbFetch<GovernanceAIReport>(
        "v1/governance/ai-classify",
        {
          method: "POST",
          body: JSON.stringify({
            dry_run: dryRun,
            confirmation: "确认AI梳理资料密级",
          }),
        },
        token,
      );
      setGovernanceAIReport(report);
      if (!dryRun) {
        setGovernanceMessage(report.notice || `AI已先行调整 ${report.changed_count || 0} 份资料。`);
        await refreshGovernance(0);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "AI密级梳理失败");
    } finally {
      setGovernanceBusy("");
    }
  }

  async function handleReviewProposal(
    event: FormEvent<HTMLFormElement>,
    documentId: string,
  ) {
    event.preventDefault();
    if (!token) return;
    const data = new FormData(event.currentTarget);
    const rawYear = String(data.get("year") || "").trim();
    setReviewBusy(`proposal-${documentId}`);
    setReviewMessage("");
    setError("");
    try {
      const response = await kbFetch<{ notice: string }>(
        `v1/review/${documentId}/proposal`,
        {
          method: "POST",
          body: JSON.stringify({
            project_name: String(data.get("project_name") || "").trim(),
            client: String(data.get("client") || "").trim() || null,
            year: rawYear ? Number(rawYear) : null,
            domain: data.get("domain"),
            document_role: data.get("document_role"),
            version: String(data.get("version") || "").trim(),
            confidentiality: data.get("confidentiality"),
            is_final: data.get("is_final") === "on",
            note: String(data.get("note") || "").trim() || null,
          }),
        },
        token,
      );
      await refreshReviewQueue();
      setReviewEditing("");
      setReviewMessage(response.notice);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "信息保存失败");
    } finally {
      setReviewBusy("");
    }
  }

  async function handlePublishReview(
    event: FormEvent<HTMLFormElement>,
    item: ReviewItem,
  ) {
    event.preventDefault();
    if (!token) return;
    const data = new FormData(event.currentTarget);
    setReviewBusy(`publish-${item.document_id}`);
    setReviewMessage("");
    setError("");
    try {
      const response = await kbFetch<{ notice: string }>(
        `v1/review/${item.document_id}/publish`,
        {
          method: "POST",
          body: JSON.stringify({
            confirmation: data.get("confirmation"),
            supersedes_document_ids: item.replacement_candidates.map(
              (candidate) => candidate.document_id,
            ),
            note: String(data.get("note") || "").trim() || null,
          }),
        },
        token,
      );
      const [queue, service, projectRows] = await Promise.all([
        kbFetch<ReviewItem[]>("v1/review/queue", {}, token),
        kbFetch<Status>("v1/status", {}, token),
        kbFetch<Project[]>("v1/projects", {}, token),
      ]);
      setReviewQueue(queue);
      setStatus(service);
      setProjects(projectRows);
      setReviewMessage(response.notice);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "当前版本发布失败");
    } finally {
      setReviewBusy("");
    }
  }

  async function handleReconcileSources() {
    if (!token) return;
    setSourceReconcileBusy(true);
    setError("");
    try {
      await kbFetch(
        "v1/operations/reconcile-sources",
        { method: "POST" },
        token,
      );
      const [operationState, queue, service] = await Promise.all([
        kbFetch<OperationsStatus>("v1/operations/status", {}, token),
        kbFetch<ReviewItem[]>("v1/review/queue", {}, token),
        kbFetch<Status>("v1/status", {}, token),
      ]);
      setOperations(operationState);
      setReviewQueue(queue);
      setStatus(service);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "原件完整性核验失败");
    } finally {
      setSourceReconcileBusy(false);
    }
  }

  async function handleCreateAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setAccountBusy("create");
    setError("");
    try {
      await kbFetch<AdminUser>(
        "v1/admin/users",
        {
          method: "POST",
          body: JSON.stringify({
            username: String(data.get("username") || "").trim(),
            display_name: String(data.get("display_name") || "").trim(),
            password: data.get("password"),
            role: data.get("role"),
            confidentiality_ceiling: data.get("confidentiality_ceiling"),
          }),
        },
        token,
      );
      setAccounts(await kbFetch<AdminUser[]>("v1/admin/users", {}, token));
      form.reset();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "账号创建失败");
    } finally {
      setAccountBusy("");
    }
  }

  async function handleCreateCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setCategoryBusy("create");
    setError("");
    try {
      await kbFetch<KnowledgeCategory>(
        "v1/admin/categories",
        {
          method: "POST",
          body: JSON.stringify({ name: String(data.get("name") || "").trim() }),
        },
        token,
      );
      setCategories(await kbFetch<KnowledgeCategory[]>("v1/categories", {}, token));
      form.reset();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "资料分类创建失败");
    } finally {
      setCategoryBusy("");
    }
  }

  async function handleCategoryName(
    event: FormEvent<HTMLFormElement>,
    category: KnowledgeCategory,
  ) {
    event.preventDefault();
    if (!token) return;
    const data = new FormData(event.currentTarget);
    setCategoryBusy(category.id);
    setError("");
    try {
      await kbFetch<KnowledgeCategory>(
        `v1/admin/categories/${category.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ name: String(data.get("name") || "").trim() }),
        },
        token,
      );
      setCategories(await kbFetch<KnowledgeCategory[]>("v1/categories", {}, token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "资料分类保存失败");
    } finally {
      setCategoryBusy("");
    }
  }

  async function handleCategoryActive(category: KnowledgeCategory) {
    if (!token) return;
    setCategoryBusy(category.id);
    setError("");
    try {
      await kbFetch<KnowledgeCategory>(
        `v1/admin/categories/${category.id}`,
        { method: "PATCH", body: JSON.stringify({ active: !category.active }) },
        token,
      );
      setCategories(await kbFetch<KnowledgeCategory[]>("v1/categories", {}, token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "资料分类状态修改失败");
    } finally {
      setCategoryBusy("");
    }
  }

  async function handleAccountPolicy(
    event: FormEvent<HTMLFormElement>,
    accountId: string,
  ) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setAccountBusy(accountId);
    setError("");
    try {
      await kbFetch<AdminUser>(
        `v1/admin/users/${accountId}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            role: data.get("role"),
            confidentiality_ceiling: data.get("confidentiality_ceiling"),
          }),
        },
        token,
      );
      setAccounts(await kbFetch<AdminUser[]>("v1/admin/users", {}, token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "权限保存失败");
    } finally {
      setAccountBusy("");
    }
  }

  async function handleAccountActive(account: AdminUser) {
    setAccountBusy(account.id);
    setError("");
    try {
      await kbFetch<AdminUser>(
        `v1/admin/users/${account.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ active: !account.active }),
        },
        token,
      );
      setAccounts(await kbFetch<AdminUser[]>("v1/admin/users", {}, token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "账号状态修改失败");
    } finally {
      setAccountBusy("");
    }
  }

  async function handleResetPassword(
    event: FormEvent<HTMLFormElement>,
    accountId: string,
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setAccountBusy(`password-${accountId}`);
    setError("");
    try {
      await kbFetch(
        `v1/admin/users/${accountId}/password`,
        {
          method: "POST",
          body: JSON.stringify({ password: data.get("password") }),
        },
        token,
      );
      form.reset();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "密码重置失败");
    } finally {
      setAccountBusy("");
    }
  }

  async function handleOwnPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setAccountBusy("own-password");
    setError("");
    try {
      await kbFetch(
        "v1/me/password",
        {
          method: "POST",
          body: JSON.stringify({
            current_password: data.get("current_password"),
            new_password: data.get("new_password"),
          }),
        },
        token,
      );
      sessionStorage.removeItem(TOKEN_KEY);
      setShowPasswordForm(false);
      setToken("");
      setUser(null);
      setStatus(null);
      setError("密码已修改，请使用新密码重新登录。");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "密码修改失败");
    } finally {
      setAccountBusy("");
    }
  }

  const readyDocuments = useMemo(
    () => reviewQueue.filter((item) => !item.issue).length,
    [reviewQueue],
  );
  const batchEligibleReviewIds = useMemo(
    () => reviewQueue
      .filter((item) => (
        item.confirm_eligible
        && item.knowledge_status === "candidate"
        && ["L1", "L2", "L3"].includes(item.confidentiality)
      ))
      .map((item) => item.document_id),
    [reviewQueue],
  );
  const batchReviewCandidateIds = useMemo(
    () => reviewQueue
      .filter((item) => (
        item.knowledge_status === "candidate"
        && ["L1", "L2", "L3"].includes(item.confidentiality)
      ))
      .map((item) => item.document_id),
    [reviewQueue],
  );
  const categoryNames = useMemo(
    () => ({
      ...defaultCategoryNames,
      ...Object.fromEntries(categories.map((item) => [item.key, item.name])),
    }),
    [categories],
  );
  const activeCategories = useMemo(
    () => categories.filter((item) => item.active),
    [categories],
  );
  const uploadCategories = activeCategories;
  const uploadDepartments = useMemo(
    () => uploadCategories.map((item) => item.key),
    [uploadCategories],
  );
  const writingCategories = activeCategories;
  const uploadConfidentialityOptions = useMemo(() => {
    const ranks: Record<string, number> = { L1: 1, L2: 2, L3: 3, L4: 4, L5: 5 };
    const ceiling = ranks[user?.confidentiality_ceiling || "L1"] || 1;
    return Object.keys(ranks).filter((level) => ranks[level] <= ceiling);
  }, [user?.confidentiality_ceiling]);
  const selectedContractCategory = contractCategories.find(
    (item) => item.key === contractCategory,
  ) || null;
  const canUploadContracts = Boolean(selectedContractCategory?.can_upload);
  const canManageContractFolders = Boolean(
    (user?.organization_role === "administrative" && ["L4", "L5"].includes(user?.confidentiality_ceiling || ""))
    || (user?.organization_role === "management" && user?.confidentiality_ceiling === "L5"),
  );
  const contractDocumentGroups = useMemo(() => {
    const grouped = new Map<string, ContractDocument[]>();
    for (const document of contractDocuments) {
      const folder = document.folder_path?.trim() || "未分文件夹";
      grouped.set(folder, [...(grouped.get(folder) || []), document]);
    }
    return Array.from(grouped.entries()).map(([folder, documents]) => ({ folder, documents }));
  }, [contractDocuments]);
  const confidentialityRank = ({ L1: 1, L2: 2, L3: 3, L4: 4, L5: 5 } as Record<string, number>)[user?.confidentiality_ceiling || "L1"] || 1;
  const canUseFinance = (
    (user?.organization_role === "finance" && confidentialityRank >= 4)
    || (user?.organization_role === "management" && confidentialityRank >= 5)
  );
  const canEditBankStatements = user?.organization_role === "finance" && confidentialityRank >= 4;
  const isNamedExecutive = user?.organization_role === "management"
    && user?.confidentiality_ceiling === "L5"
    && ["found", "founder", "jaanliyuan"].includes(user?.username.toLowerCase() || "");
  const canEditCash = canEditBankStatements || isNamedExecutive;
  const canUseManagedProjects = (
    user?.organization_role === "business"
    || user?.organization_role === "education"
    || canEditBankStatements
    || (user?.organization_role === "management" && confidentialityRank >= 5)
  );
  const canCreateManagedProject = user?.organization_role === "business";
  const canReviewManagedProject = user?.organization_role === "management"
    && user?.confidentiality_ceiling === "L5"
    && ["found", "founder"].includes(user?.username.toLowerCase() || "");
  const canArchiveManagedProject = canEditBankStatements
    || (user?.organization_role === "management" && confidentialityRank >= 5);
  const selectedFinanceEntity = financeEntities.find(
    (item) => item.id === selectedFinanceEntityId,
  ) || null;
  const selectedFinanceProjects = selectedFinanceEntity
    ? managedProjects.items.filter((project) => {
        const aliases: Record<FinanceEntity["key"], string[]> = {
          jingao: ["京奥电竞（北京）科技有限公司", "京奥电竞", "京奥"],
          "ace-leopard": ["王牌猎豹", "JAG三角洲", "三角洲"],
          "power-leopard": ["劲腾豹跃", "JAG王者", "王者"],
          "xingyao": ["星曜电竞"],
        };
        const companyName = project.company_name.trim();
        return [
          selectedFinanceEntity.name,
          selectedFinanceEntity.display_name,
          selectedFinanceEntity.business_name,
          ...aliases[selectedFinanceEntity.key],
        ].some((alias) => alias && (companyName === alias || companyName.includes(alias)));
      })
    : [];
  const visibleTabs = useMemo(
    () => tabs.filter((item) => {
      if (item.name === "入库审核") {
        return ["founder", "knowledge_admin", "department_owner"].includes(user?.role || "");
      }
      if (item.name === "资料治理") {
        return ["founder", "knowledge_admin"].includes(user?.role || "");
      }
      if (item.name === "系统状态") {
        return ["founder", "knowledge_admin"].includes(user?.role || "");
      }
      if (item.name === "账号管理") return user?.role === "founder";
      if (item.name === "合同档案库") {
        return (
          ({ L1: 1, L2: 2, L3: 3, L4: 4, L5: 5 } as Record<string, number>)[user?.confidentiality_ceiling || "L1"] >= 4
          && ["administrative", "personnel", "finance", "management"].includes(user?.organization_role || "")
        );
      }
      if (item.name === "财务分析") return canUseFinance;
      if (item.name === "项目管理") return canUseManagedProjects;
      return true;
    }),
    [canUseFinance, canUseManagedProjects, user?.role, user?.confidentiality_ceiling, user?.organization_role],
  );
  const mobilePrimaryTabs = useMemo(
    () => visibleTabs.filter((item) => mobilePrimaryTabNames.includes(item.name)),
    [visibleTabs],
  );
  const mobileMoreTabs = useMemo(
    () => visibleTabs.filter((item) => !mobilePrimaryTabNames.includes(item.name)),
    [visibleTabs],
  );
  const mobileMoreActive = mobileMoreTabs.some((item) => item.name === active);

  if (initializing) {
    return (
      <main className="loadingScreen">
        <div className="loadingMark">J</div>
        <p>正在连接京奥AI智能运营系统…</p>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="loginScreen">
        <section className="loginBrand">
          {/* The logo is a bundled intranet asset. A native image avoids the
              Cloudflare image optimizer, which is unavailable in local/NAS
              deployments. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/jingao-mark-transparent.png"
            alt="京奥电竞"
            width={512}
            height={512}
          />
          <div className="loginBrandCopy">
            <span>JAOS</span>
            <h1>让公司的每一次实践，<br />都成为下一次工作的起点。</h1>
            <p>京奥电竞内部智能运营平台 · 全程可追溯</p>
          </div>
        </section>
        <section className="loginCard">
          <div>
            <p className="eyebrow">INTERNAL ACCESS</p>
            <h2>登录京奥AI智能运营系统</h2>
            <p className="loginHint">测试期采用本地账号。正式接入飞书前，账号仅由管理员创建。</p>
          </div>
          <form onSubmit={handleLogin}>
            <label>
              账号
              <input name="username" defaultValue="founder" autoComplete="username" />
            </label>
            <label>
              密码
              <input name="password" type="password" autoComplete="current-password" />
            </label>
            {error && <p className="formError">{error}</p>}
            <button type="submit" disabled={loginBusy}>
              {loginBusy ? "正在验证…" : "进入系统"}
            </button>
          </form>
          <small>仅限京奥电竞授权成员使用</small>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="logoFrame">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/jingao-mark-transparent.png"
              alt="京奥电竞"
              width={512}
              height={512}
            />
          </div>
          <div className="brandCopy"><strong>京奥AI智能运营系统</strong><span>JAOS</span></div>
        </div>
        <nav aria-label="主导航">
          {visibleTabs.map((item) => (
            <Fragment key={item.name}>
              <button
                type="button"
                className={active === item.name ? "active" : ""}
                onClick={() => navigateToTab(item.name)}
              >
                <span className="navIcon">{item.icon}</span>
                <span className="navLabel">{item.name}</span>
                {item.name === "入库审核" && reviewQueue.length > 0 && (
                  <b className="navCount">{reviewQueue.length}</b>
                )}
              </button>
              {item.name === "财务分析" && financeEntities.length > 0 && (
                <div className="financeEntitySubnav" aria-label="财务公司账套">
                  {financeEntities.map((entity) => (
                    <button
                      type="button"
                      className={active === "财务分析" && selectedFinanceEntityId === entity.id ? "active" : ""}
                      onClick={() => handleFinanceEntitySelect(entity.id)}
                      key={entity.id}
                    >
                      <span>{entity.display_name}</span>
                      <small>{entity.business_name}</small>
                    </button>
                  ))}
                </div>
              )}
            </Fragment>
          ))}
        </nav>
        <div className="trial">
          <span className="pulse" />
          <div>
            <strong>本地安全测试</strong>
            <small>{status?.retrieval.outbound_enabled ? "已启用出网" : "当前资料不出网"}</small>
          </div>
        </div>
        <div className="user">
          <div className="avatar">{user.display_name.slice(0, 1)}</div>
          <div><strong>{user.display_name}</strong><small>{userRoleNames[user.organization_role] || user.organization_role} · {confidentialityLabel(user.confidentiality_ceiling)}</small></div>
          <div className="userActions">
            <button type="button" onClick={() => setShowPasswordForm(true)}>改密</button>
            <button type="button" onClick={handleLogout}>退出</button>
          </div>
        </div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">京奥AI智能运营系统 · JAOS</p>
            <h1>{active}</h1>
          </div>
          <div className="topActions">
            <span className={`systemState ${operations?.status || ""}`}>
              <i /> Agent {
                operations?.status === "critical"
                  ? "异常"
                  : operations?.status === "warning"
                  ? "需关注"
                  : status?.status === "ready"
                  ? "在线"
                  : "检查中"
              }
            </span>
            {["founder", "knowledge_admin", "department_owner"].includes(user.role) ? (
              <button type="button" className="primaryButton" onClick={() => navigateToTab("入库审核")}>
                查看入库队列
              </button>
            ) : (
              <button type="button" className="primaryButton" onClick={() => navigateToTab("资料上传")}>
                上传资料
              </button>
            )}
          </div>
        </header>

        {error && <div className="globalError" role="alert" aria-live="assertive">{error}<button type="button" aria-label="关闭错误提示" onClick={() => setError("")}>×</button></div>}

        {active === "工作台" && (
          <>
            <section className="hero">
              <div className="heroCopy">
                <span className="tag">SOURCE-GROUNDED KNOWLEDGE</span>
                <h2>先找到证据，<br /><em>再形成答案。</em></h2>
                <p>资料经预览确认后进入历史知识库；公司介绍等现行口径单独维护当前版本。所有结果保留文件名、版本与页码。</p>
                <form className="ask" onSubmit={handleSearch}>
                  <span>✦</span>
                  <input
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder="例如：解说训练营方案里有哪些课程模块？"
                    aria-label="向京奥AI智能运营系统提问"
                  />
                  <button disabled={searching}>{searching ? "检索中…" : "检索"}</button>
                </form>
                {searchResponse && <div ref={searchResultRef}><CompactAnswer response={searchResponse} /></div>}
              </div>
              <div className="evidenceVisual" aria-hidden="true">
                <div className="evidenceRing ringOne" />
                <div className="evidenceRing ringTwo" />
                <div className="evidenceCore">
                  <strong>{status?.counts.documents ?? 0}</strong>
                  <span>份知识资料</span>
                </div>
                <span className="evidenceNode nodeOne">原文</span>
                <span className="evidenceNode nodeTwo">页码</span>
                <span className="evidenceNode nodeThree">权限</span>
              </div>
            </section>

            <section className="stats">
              <StatCard tone="blue" label="候选项目" value={status?.counts.projects ?? 0} note="等待业务确认" />
              <StatCard tone="red" label="登记文件" value={status?.counts.documents ?? 0} note={`${status?.counts.source_available_documents ?? readyDocuments} 份原件可核验`} />
              <StatCard tone="green" label="可检索文件" value={readyDocuments} note="本地全文检索" />
              <StatCard tone="orange" label="当前事实" value={status?.counts.current_documents ?? 0} note="未经批准保持为 0" />
            </section>

            <section className="workspaceGrid">
              <section className="panel">
                <PanelTitle eyebrow="RECENT INGESTION" title="最新候选项目" action="检索资料" onAction={() => setActive("AI资料检索")} />
                <ProjectRows projects={projects.slice(0, 5)} categoryNames={categoryNames} />
              </section>
              <section className="panel quickPanel">
                <PanelTitle eyebrow="NEXT ACTION" title="从真实工作开始" />
                <QuickAction icon="✦" title="AI资料检索" note="按页码查看候选证据" onClick={() => setActive("AI资料检索")} />
                <QuickAction icon="✎" title="用智库写材料" note="自由描述，自动引用内部资料" onClick={() => setActive("智能创作")} />
                {["founder", "knowledge_admin", "department_owner"].includes(user.role) ? (
                  <QuickAction icon="✓" title="处理入库资料" note={`${reviewQueue.length} 份资料等待确认`} onClick={() => setActive("入库审核")} />
                ) : (
                  <QuickAction icon="↑" title="上传工作资料" note="网页直接上传到授权分类" onClick={() => setActive("资料上传")} />
                )}
              </section>
            </section>
          </>
        )}

        {active === "财务分析" && selectedFinanceEntity && (
          <FinanceWorkspace
            key={selectedFinanceEntity.id}
            token={token}
            user={user}
            entity={selectedFinanceEntity}
            entities={financeEntities}
            dashboard={financeDashboard}
            periodView={financePeriodView}
            annualYears={financeAnnualYears}
            annualDashboard={financeAnnualDashboard}
            batches={financeBatches}
            cashEntries={financeCash}
            transfers={financeTransfers}
            purposeCorrections={financePurposeCorrections}
            includeInternalTransfers={financeIncludeInternalTransfers}
            selectedBatch={selectedFinanceBatch}
            transactions={financeTransactions}
            busy={financeBusy}
            message={financeMessage}
            uploadError={financeUploadError}
            canEditBank={canEditBankStatements}
            canDeleteConfirmedBatch={canReviewManagedProject}
            canReviewPurposeCorrections={canReviewManagedProject}
            canEditCash={canEditCash && selectedFinanceEntity.show_cash}
            projects={selectedFinanceProjects}
            onEntitySelect={handleFinanceEntitySelect}
            onPeriodViewChange={setFinancePeriodView}
            onTransferScopeChange={setFinanceIncludeInternalTransfers}
            onTransferDecision={handleFinanceTransferDecision}
            onReceivablePayableCreate={handleFinanceReceivablePayableCreate}
            onReceivablePayableUpdate={handleFinanceReceivablePayableUpdate}
            onUpload={handleStatementUpload}
            onCashEntry={handleCashEntry}
            onSelectBatch={handleFinanceBatchSelect}
            onConfirmBatch={handleConfirmStatement}
            onDeleteBatch={handleDeleteStatement}
            onUpdateTransaction={handleTransactionUpdate}
            onPurposeCorrectionRequest={handlePurposeCorrectionRequest}
            onPurposeCorrectionReview={handlePurposeCorrectionReview}
          />
        )}

        {active === "财务分析" && !selectedFinanceEntity && (
          <section className="panel financeEntityLoading">
            <p className="eyebrow">FINANCE ENTITY</p>
            <h2>正在加载公司财务账套…</h2>
          </section>
        )}

        {active === "项目管理" && (
          <>
          {(user.organization_role === "education" || canUseFinance) && <div className="educationModuleTabs" aria-label="项目管理模块">
            {user.organization_role !== "education" && <button type="button" className={projectModule === "standard" ? "active" : ""} onClick={() => setProjectModule("standard")}>业务项目</button>}
            <button type="button" className={projectModule === "education" ? "active" : ""} onClick={() => setProjectModule("education")}>星曜教培 · 班期管理</button>
            <button type="button" className={projectModule === "education-ledger" || (user.organization_role === "education" && projectModule === "standard") ? "active" : ""} onClick={() => setProjectModule("education-ledger")}>教培综合台账</button>
          </div>}
          {(user.organization_role === "education" || (canUseFinance && ["education", "education-ledger"].includes(projectModule))) ? <EducationWorkspace key={projectModule} api={kbFetch} token={token || ""} initialModule={projectModule === "education" ? "cohorts" : "ledger"} /> :
          <ProjectManagementWorkspace
            user={user}
            registry={managedProjects}
            selected={selectedManagedProject}
            collaboratorCandidates={projectCollaboratorCandidates}
            busy={projectBusy}
            message={projectMessage}
            canCreate={canCreateManagedProject}
            canReview={canReviewManagedProject}
            canArchive={canArchiveManagedProject}
            canFinanceConfirm={canEditBankStatements}
            deletePasswordConfigured={projectDeletePasswordConfigured}
            onCreate={handleCreateManagedProject}
            onUpdate={handleUpdateManagedProject}
            onCollaborators={handleProjectCollaborators}
            onContractStatus={handleUpdateProjectContractStatus}
            onProcessFinance={handleProjectProcessFinance}
            onRequestDeletion={handleRequestProjectDeletion}
            onDeletionDecision={handleProjectDeletionDecision}
            onConfigureDeletePassword={handleConfigureProjectDeletePassword}
            onFounderDelete={handleFounderProjectDelete}
            onArchive={handleProjectArchive}
            onSelect={handleManagedProjectSelect}
            onCashflow={handleProjectCashflow}
            onCashflowActual={handleProjectCashflowActual}
            onSubmitInitiation={handleSubmitInitiation}
            onProgress={handleProjectProgress}
            onSubmitClosing={handleSubmitClosing}
            onReview={handleProjectReview}
          />
          }
          </>
        )}

        {active === "资料上传" && (
          <section className="uploadLayout">
            <section className="panel uploadPanel">
              <PanelTitle eyebrow="EMPLOYEE UPLOAD" title="上传工作资料" />
              <div className="noticeBar">
                <strong>文档审核，素材直入</strong>
                <span>Office、PDF 和文本资料进入审核；图片、视频、音频、设计源文件等素材自动入库。原文件始终保存在 NAS。</span>
              </div>
              <form className="uploadForm" onSubmit={handleUpload}>
                <div className="uploadPickerGrid">
                  <label className="uploadDropzone">
                    <input
                      type="file"
                      multiple
                      accept=".pdf,.pptx,.doc,.docm,.docx,.xls,.xlsx,.xlsm,.txt,.md,.png,.jpg,.jpeg,.webp,.mp4,.webm,.mov,.m4v,.mp3,.m4a,.wav,.flac,.mm,.ai,.zip"
                      onChange={(event) => {
                        const files = Array.from(event.target.files || []).slice(0, 20);
                        setUploadFiles(files);
                        setUploadFolderName("");
                        setUploadMessage("");
                        setUploadProgress(0);
                      }}
                    />
                    <span className="uploadDropIcon">↑</span>
                    <strong>选择若干文件</strong>
                    <small>适合 Office、PDF 或少量素材；一次最多 20 份</small>
                  </label>
                  <label className="uploadDropzone folderDropzone">
                    <input
                      type="file"
                      multiple
                      {...({ webkitdirectory: "" } as Record<string, string>)}
                      onChange={(event) => {
                        const supported = /\.(pdf|pptx|doc|docm|docx|xls|xlsx|xlsm|txt|md|png|jpg|jpeg|webp|mp4|webm|mov|m4v|mp3|m4a|wav|flac|mm|ai|zip)$/i;
                        const selected = Array.from(event.target.files || []);
                        const files = selected.filter((file) => supported.test(file.name)).slice(0, 500);
                        const rootName = files[0]?.webkitRelativePath.split("/")[0] || "";
                        setUploadFiles(files);
                        setUploadFolderName(rootName);
                        setUploadMessage(selected.length > files.length ? `已忽略 ${selected.length - files.length} 个不支持或超出上限的文件。` : "");
                        setUploadProgress(0);
                      }}
                    />
                    <span className="uploadDropIcon">▣</span>
                    <strong>上传一个素材文件夹</strong>
                    <small>文件夹名作为整批素材名称；最多 500 份。网络中断会自动重试，已成功文件不会重复上传</small>
                  </label>
                </div>

                {uploadFiles.length > 0 && (
                  <div className="uploadFileList">
                    {uploadFolderName && (
                      <span className="folderSelectionSummary">
                        <b>素材文件夹：{uploadFolderName}</b>
                        <small>{uploadFiles.length} 份文件</small>
                      </span>
                    )}
                    {!uploadFolderName && uploadFiles.map((file) => (
                      <span key={`${file.name}-${file.size}`}>
                        <b>{file.name}</b>
                        <small>{(file.size / 1024 / 1024).toFixed(1)} MB</small>
                      </span>
                    ))}
                  </div>
                )}

                <div className="uploadOptions">
                  <label>
                    资料分类
                    <select
                      value={uploadDepartment}
                      onChange={(event) => setUploadDepartment(event.target.value)}
                    >
                      {uploadCategories.map((item) => (
                        <option key={item.key} value={item.key}>{item.name}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    资料密级
                    <select
                      value={uploadConfidentiality}
                      onChange={(event) => setUploadConfidentiality(event.target.value)}
                    >
                      {uploadConfidentialityOptions.map((level) => (
                        <option key={level} value={level}>{confidentialityLabel(level)}</option>
                      ))}
                    </select>
                  </label>
                </div>

                {uploadBusy && (
                  <div className="uploadProgress" aria-live="polite">
                    <div><span style={{ width: `${uploadProgress}%` }} /></div>
                    <b>{uploadProgress}%</b>
                  </div>
                )}
                {uploadMessage && (
                  <div className="noticeBar successNotice">
                    <strong>上传完成</strong><span>{uploadMessage}</span>
                  </div>
                )}
                <button
                  type="submit"
                  className="primaryButton uploadSubmit"
                  disabled={uploadBusy || uploadFiles.length === 0 || uploadDepartments.length === 0}
                >
                  {uploadBusy ? "正在上传，请不要关闭页面…" : "上传资料"}
                </button>
              </form>
            </section>
            <aside className="panel uploadGuide">
              <p className="eyebrow">UPLOAD GUIDE</p>
              <h2>员工只需要做两件事</h2>
              <ol>
                <li><b>选择资料分类</b><span>系统按账号权限只显示你可使用的分类。</span></li>
                <li><b>选择文件并上传</b><span>内容文档由负责人审核；图片、音视频等素材无需等待审核。</span></li>
              </ol>
              <div className="videoSupport">
                <strong>视频可以预览</strong>
                <p>MP4、WebM 可直接在线播放；MOV/M4V 是否直接播放取决于浏览器编码，无法播放时仍可下载原件。</p>
              </div>
            </aside>
          </section>
        )}

        {active === "合同档案库" && (
          <section className="contractArchive">
            <section className="panel contractHeader">
              <PanelTitle eyebrow="CONTRACT ARCHIVE" title="合同档案库" />
              <div className="contractSecurityNotice">
                <strong>本地最高级别保护</strong>
                <span>行政可检索行政及业务合同，人事可上传、检索人事合同；行政、人事、财务均可上传总办涉密合同，并且只能检索、预览本人上传的总办合同。管理+L5可查阅全部合同。合同全文、OCR和检索词均不发送到云端模型。</span>
              </div>
              <div className="contractCategoryTabs">
                {contractCategories.map((item) => (
                  <button
                    type="button"
                    key={item.key}
                    className={contractCategory === item.key ? "active" : ""}
                    onClick={() => {
                      setContractCategory(item.key);
                      setContractSearchResponse(null);
                      setContractFiles([]);
                      setContractFolderName("");
                      setContractPendingCount(0);
                      setContractMessage("");
                    }}
                  >
                    <b>{item.name}</b>
                    <small>
                      {confidentialityLabel(item.confidentiality)}
                      {item.search_scope === "own" ? " · 仅本人上传" : !item.can_search && item.can_upload ? " · 仅上传" : ""}
                    </small>
                  </button>
                ))}
              </div>
              {contractCategoriesLoading && contractCategories.length === 0 && (
                <div className="noticeBar">
                  <strong>正在读取合同权限</strong>
                  <span>系统正在核验账号角色、L5权限和可访问合同分类。</span>
                </div>
              )}
              {contractCategoriesError && (
                <div className="noticeBar errorNotice" role="alert">
                  <strong>合同权限暂时加载失败</strong>
                  <span>{contractCategoriesError}。这不是账号降权，请重新加载。</span>
                  <button type="button" className="secondaryButton" onClick={() => setContractCategoriesReloadKey((value) => value + 1)}>
                    重新加载合同权限
                  </button>
                </div>
              )}
            </section>

            <section className={`contractGrid ${!canUploadContracts ? "searchOnly" : ""}`}>
              {canUploadContracts && (
              <section className="panel contractUploadPanel">
                <PanelTitle eyebrow="SECURE UPLOAD" title="上传合同原件" />
                <p>支持扫描PDF和Word，也可直接选择一个合同文件夹。散件由本地AI根据标题和正文自动归档，文件夹上传则保留原层级；L4/L5合同内容不发送到云端。</p>
                <form onSubmit={handleContractUpload}>
                  <div className="contractPickerGrid">
                    <label className="contractFilePicker">
                      <input
                        type="file"
                        multiple
                        accept=".pdf,.doc,.docm,.docx"
                        onChange={(event) => {
                          setContractSelectionMode("files");
                          setContractFolderName("");
                          setContractFiles(Array.from(event.target.files || []).slice(0, 20));
                          setContractMessage("");
                        }}
                      />
                      <b>选择合同文件</b>
                      <small>适合少量PDF或Word合同，一次最多20份</small>
                    </label>
                    <label className="contractFilePicker folderPicker">
                      <input
                        type="file"
                        multiple
                        accept=".pdf,.doc,.docm,.docx"
                        {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
                        onChange={(event) => {
                          const selected = Array.from(event.target.files || []);
                          const supported = /\.(pdf|doc|docm|docx)$/i;
                          const files = selected.filter((file) => supported.test(file.name)).slice(0, 200);
                          const firstPath = files[0]?.webkitRelativePath || "";
                          const rootFolder = firstPath.split("/").filter(Boolean)[0] || "所选文件夹";
                          setContractSelectionMode("folder");
                          setContractFolderName(rootFolder);
                          setContractFiles(files);
                          setContractMessage(
                            selected.length > files.length
                              ? `已忽略 ${selected.length - files.length} 个不支持或超出上限的文件。`
                              : "",
                          );
                        }}
                      />
                      <b>选择合同文件夹</b>
                      <small>保留系列合同的文件夹层级，最多200份</small>
                    </label>
                  </div>
                  {contractFiles.length > 0 && (
                    <div className="contractSelectionSummary">
                      <div>
                        <strong>
                          {contractSelectionMode === "folder"
                            ? `合同文件夹：${contractFolderName}`
                            : `已选择 ${contractFiles.length} 份合同`}
                        </strong>
                        <span>
                          {contractSelectionMode === "folder"
                            ? `共 ${contractFiles.length} 份支持的合同；上传后会在 NAS 自动重建这个文件夹及其子目录。`
                            : "所选合同将逐份进入入库审核。"}
                        </span>
                      </div>
                      <details className="contractSelectedFiles">
                        <summary>查看文件清单</summary>
                        <div>
                          {contractFiles.map((file) => (
                            <span key={`${file.webkitRelativePath || file.name}-${file.size}`}>
                              {file.webkitRelativePath || file.name}
                            </span>
                          ))}
                        </div>
                      </details>
                    </div>
                  )}
                  <button className="primaryButton" disabled={contractBusy || !contractFiles.length || !contractCategory}>
                    {contractBusy
                      ? `正在上传 ${contractUploadProgress.completed}/${contractUploadProgress.total}`
                      : contractSelectionMode === "folder" && contractFiles.length
                        ? `上传整个文件夹（${contractFiles.length}份）`
                        : "上传并进入审核"}
                  </button>
                </form>
                {contractMessage && (
                  <div className="noticeBar successNotice contractUploadSuccess">
                    <span>{contractMessage}</span>
                    {["founder", "knowledge_admin", "department_owner"].includes(user?.role || "") && (
                      <button type="button" onClick={() => navigateToTab("入库审核")}>前往入库审核</button>
                    )}
                  </div>
                )}
              </section>
              )}

              {!selectedContractCategory ? (
                <section className="panel contractSearchPanel">
                  <PanelTitle
                    eyebrow="ACCESS CHECK"
                    title={contractCategoriesLoading ? "正在核验合同权限" : "合同权限尚未加载"}
                  />
                  <p>合同分类返回后才会显示上传、检索和全部合同，不会再把加载失败误显示为“仅可上传”。</p>
                </section>
              ) : selectedContractCategory.can_search ? (
              <section className="panel contractSearchPanel">
                <PanelTitle eyebrow="LOCAL SEARCH" title="本地合同检索" />
                {selectedContractCategory?.search_scope === "own" && (
                  <div className="noticeBar">
                    <strong>仅本人上传范围</strong>
                    <span>这里只会检索和显示你本人上传的总办合同；其他人上传的涉密合同不会暴露标题、数量或搜索结果。</span>
                  </div>
                )}
                <form onSubmit={handleContractSearch}>
                  <input
                    value={contractQuery}
                    onChange={(event) => setContractQuery(event.target.value)}
                    placeholder="输入合同名称、甲乙方、事项或OCR关键词…"
                  />
                  <button className="primaryButton" disabled={contractBusy || !contractQuery.trim()}>
                    {contractBusy ? "检索中…" : "检索当前分类"}
                  </button>
                </form>
                <div className="searchPolicy">
                  <span>权限过滤在检索前</span><span>L4/L5永不出网</span><span>操作全程审计</span>
                </div>
              </section>
              ) : (
                <section className="panel contractSearchPanel">
                  <PanelTitle eyebrow="UPLOAD ONLY" title="当前分类仅可上传" />
                  <p>行政可代为上传该分类合同，但无权检索或查看其合同内容。</p>
                </section>
              )}
            </section>

            {selectedContractCategory && (
            <section className="panel contractOwnLibrary">
              <div className="contractOwnHeader">
                <PanelTitle eyebrow="MY CONTRACTS" title={`我上传的合同（${ownedContractDocuments.length}）`} />
                <p>包含待审核与已审核合同。行政可新建文件夹，并将本人上传的合同移到其他合同分类；移入总办合同会自动升级为L5并同步NAS路径和查看权限。</p>
              </div>
              {canManageContractFolders && (
                <form className="contractFolderCreate" onSubmit={handleContractFolderCreate}>
                  <label>
                    合同分类
                    <select
                      value={contractNewFolderCategory}
                      onChange={(event) => setContractNewFolderCategory(event.target.value)}
                    >
                      {contractCategories.filter((item) => item.can_upload).map((item) => (
                        <option value={item.key} key={item.key}>{item.name}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    新文件夹名称
                    <input
                      value={contractNewFolderPath}
                      onChange={(event) => setContractNewFolderPath(event.target.value)}
                      placeholder="例如：2026年/场馆租赁合同"
                      maxLength={400}
                    />
                  </label>
                  <button className="secondaryButton" disabled={contractManageBusy === "create" || !contractNewFolderPath.trim()}>
                    {contractManageBusy === "create" ? "正在创建…" : "新建文件夹"}
                  </button>
                </form>
              )}
              {ownedContractDocuments.length === 0 ? (
                <div className="emptyState"><b>▣</b><h3>你还没有上传合同</h3><p>上传后会立即出现在这里，等待审核期间也可以整理文件夹。</p></div>
              ) : (
                <div className="contractOwnList">
                  {ownedContractDocuments.map((item) => (
                    <article key={item.document_id}>
                      <div className="contractOwnIdentity">
                        <strong>{item.title}</strong>
                        <span>
                          {item.category_name} · {confidentialityLabel(item.confidentiality)} · {item.status_label}
                        </span>
                        <small>当前位置：{item.folder_path || "分类根目录"}</small>
                      </div>
                      <div className="contractOwnActions">
                        {item.source_available && !["rejected", "deleted", "quarantined"].includes(item.knowledge_status) && (
                          <button type="button" className="previewLink" onClick={() => void handlePreview(item.document_id, 1)}>
                            查看原件
                          </button>
                        )}
                        {item.can_move && (
                          <>
                            <select
                              aria-label={`移动《${item.title}》到合同分类`}
                              value={contractMoveCategories[item.document_id] ?? item.category}
                              onChange={(event) => {
                                const nextCategory = event.target.value as ContractCategory["key"];
                                setContractMoveCategories((current) => ({
                                  ...current,
                                  [item.document_id]: nextCategory,
                                }));
                                setContractMoveTargets((current) => ({
                                  ...current,
                                  [item.document_id]: "",
                                }));
                                void refreshContractFolders(nextCategory);
                              }}
                            >
                              {contractCategories.filter((category) => category.can_upload).map((category) => (
                                <option value={category.key} key={category.key}>
                                  {category.name} · {category.confidentiality}
                                </option>
                              ))}
                            </select>
                            <select
                              aria-label={`移动《${item.title}》到文件夹`}
                              value={contractMoveTargets[item.document_id] ?? item.folder_path ?? ""}
                              onFocus={() => void refreshContractFolders(
                                contractMoveCategories[item.document_id] ?? item.category,
                              )}
                              onChange={(event) => setContractMoveTargets((current) => ({
                                ...current,
                                [item.document_id]: event.target.value,
                              }))}
                            >
                              <option value="">分类根目录</option>
                              {(contractFolders[contractMoveCategories[item.document_id] ?? item.category] || []).map((folder) => (
                                <option value={folder} key={folder}>{folder}</option>
                              ))}
                            </select>
                            <button
                              type="button"
                              className="secondaryButton"
                              disabled={contractManageBusy === item.document_id}
                              onClick={() => void handleContractMove(item)}
                            >
                              {contractManageBusy === item.document_id ? "移动中…" : "移动"}
                            </button>
                          </>
                        )}
                        {contractMoveErrors[item.document_id] && (
                          <small className="contractMoveError" role="alert">
                            移动失败：{contractMoveErrors[item.document_id]}
                          </small>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
            )}

            {contractSearchResponse && (
              <section className="panel contractResults">
                <PanelTitle eyebrow="SEARCH RESULTS" title="合同检索结果" />
                <FullAnswer
                  response={contractSearchResponse}
                  previewBusy={previewBusy}
                  onPreview={handlePreview}
                />
              </section>
            )}

            {contractCategories.find((item) => item.key === contractCategory)?.can_search && (
            <section className="panel contractDocuments">
              <PanelTitle eyebrow="APPROVED FILES" title={`已审核合同（${contractDocuments.length}）`} />
              {contractPendingCount > 0 && (
                <div className="noticeBar contractPendingNotice">
                  <strong>{contractPendingCount} 份合同已安全保存，正在等待审核</strong>
                  <span>审核前不会出现在“已审核合同”或检索结果中；文件夹层级已经保存在 NAS。</span>
                </div>
              )}
              {contractDocuments.length === 0 ? (
                <div className="emptyState"><b>▣</b><h3>当前分类暂无已审核合同</h3><p>新上传合同审核通过后会显示在这里。</p></div>
              ) : (
                <div className="contractFolderGroups">
                  {contractDocumentGroups.map((group) => (
                    <section className="contractFolderGroup" key={group.folder}>
                      <header>
                        <div aria-hidden="true">▰</div>
                        <strong>{group.folder}</strong>
                        <span>{group.documents.length} 份</span>
                      </header>
                      <div className="contractDocumentList">
                        {group.documents.map((item) => (
                          <article key={item.document_id}>
                            <div>
                              <strong>{item.title}</strong>
                              <small>{confidentialityLabel(item.confidentiality)} · {item.page_count}页 · {item.citation_basis === "ocr-page" ? "本地OCR" : "原文解析"}</small>
                            </div>
                            <button type="button" onClick={() => void handlePreview(item.document_id, 1)}>
                              查看原件
                            </button>
                          </article>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              )}
            </section>
            )}
          </section>
        )}

        {active === "AI资料检索" && (
          <section className="qaLayout">
            <section className="panel questionPanel">
              <p className="eyebrow">KNOWLEDGE SEARCH</p>
              <h2>带出处检索</h2>
              <p>系统会自动判断“当前事实”或“历史案例”范围。当前事实没有获批来源时，将直接回答“资料中未找到”。</p>
              <form onSubmit={handleSearch}>
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="输入项目名称、课程主题、执行经验或需要核实的问题…"
                  rows={5}
                />
                <button className="primaryButton" disabled={searching}>
                  {searching ? "正在本地检索…" : "开始检索"}
                </button>
              </form>
              <div className="searchPolicy">
                <span>检索前权限过滤</span><span>L3/L4/L5 不出网</span><span>保留页码</span>
              </div>
            </section>
            <section className="panel answerPanel">
              {!searchResponse ? (
                <div className="emptyState"><b>✦</b><h3>答案将显示在这里</h3><p>每条结果都会标明候选/当前状态。</p></div>
              ) : (
                <div ref={searchResultRef}>
                  <FullAnswer
                    response={searchResponse}
                    previewBusy={previewBusy}
                    onPreview={handlePreview}
                    loadingMore={searchingMore}
                    onLoadMore={() => void handleLoadMoreSearch()}
                  />
                </div>
              )}
            </section>
          </section>
        )}

        {active === "智能创作" && (
          <section className="writingLayout">
            <section className="panel writingControl">
              <PanelTitle eyebrow="KNOWLEDGE WRITER" title="用智库资料写初稿" />
              <p className="writingIntro">
                直接说明你要写什么、交付对象和重点。系统会自动聚焦相关业务资料，真正调用AI生成结构化初稿；AI不可用时不会返回素材拼接稿。
              </p>
              <form className="writingForm" onSubmit={handleWriting}>
                <label>
                  写作要求
                  <textarea
                    name="instruction"
                    rows={9}
                    required
                    minLength={5}
                    value={writingInstruction}
                    onChange={(event) => setWritingInstruction(event.target.value)}
                    placeholder="例如：帮我写一份面向高校领导的电竞实训室建设方案初稿，重点说明人才培养价值，并参考公司做过的相似项目。"
                  />
                </label>
                <div className="writingOptions">
                  <label>
                    资料范围
                    <select name="category" defaultValue="">
                      <option value="">我的全部可见资料</option>
                      {writingCategories.map((item) => (
                        <option key={item.key} value={item.key}>{item.name}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    时间范围
                    <select name="scope" defaultValue="all">
                      <option value="all">当前口径 + 历史案例</option>
                      <option value="current">仅当前正式口径</option>
                      <option value="history">历史项目与案例</option>
                    </select>
                  </label>
                </div>
                {user.role === "founder" && (
                  <label className="writingL3Consent">
                    <input type="checkbox" name="allow_l3_generation" />
                    <span>
                      <b>允许本次使用 L3 资料生成</b>
                      <small>仅将本次命中的授权证据片段发送至公司AI网关；L4/L5永不出网，每次生成都需重新勾选。</small>
                    </span>
                  </label>
                )}
                <button className="primaryButton full" disabled={writingBusy}>
                  {writingBusy ? "正在筛选证据并生成方案…" : "生成高质量初稿"}
                </button>
              </form>
            </section>
            <section className="panel writingResult">
              <div ref={writingResultRef} />
              {writingBusy ? (
                <div className="writingProgress" role="status" aria-live="polite">
                  <span className="writingSpinner" aria-hidden="true" />
                  <h3>正在生成方案初稿</h3>
                  <p>正在检索相关资料、核对密级、组织方案结构并添加原页引用。</p>
                  <small>通常需要约 20–90 秒，请不要重复点击。</small>
                </div>
              ) : writingError && !writingResponse ? (
                <div className="writingFailure" role="alert">
                  <b>本次没有生成初稿</b>
                  <p>{writingError}</p>
                  <small>左侧写作要求仍然保留，可以直接再次点击“生成高质量初稿”。</small>
                </div>
              ) : !writingResponse ? (
                <div className="emptyState">
                  <b>✎</b><h3>从一句自然语言开始</h3>
                  <p>可以写方案、汇报、总结、课程材料或 PPT 大纲，具体结构由你的要求决定。</p>
                </div>
              ) : (
                <>
                  {writingError && (
                    <div className="writingInlineError" role="alert">
                      本次重新生成失败，已为你保留上一版内容：{writingError}
                    </div>
                  )}
                  <div className="resultHeader">
                    <div><p className="eyebrow">AI-GENERATED DRAFT</p><h2>智库方案初稿</h2></div>
                    <div className="proposalHeaderActions">
                      <span>AI 已生成</span>
                      <button
                        type="button"
                        className={writingDraftView === "preview" ? "active" : ""}
                        onClick={() => setWritingDraftView("preview")}
                      >阅读排版</button>
                      <button
                        type="button"
                        className={writingDraftView === "edit" ? "active" : ""}
                        onClick={() => setWritingDraftView("edit")}
                      >编辑原文</button>
                      <button
                        type="button"
                        onClick={() => void navigator.clipboard.writeText(writingDraftText)}
                      >复制全文</button>
                    </div>
                  </div>
                  <div className="writingGenerationMeta">
                    <span>{writingResponse.category_auto_inferred ? `自动聚焦：${writingResponse.effective_category_name}` : writingResponse.effective_category_name || "跨分类检索"}</span>
                    <span>{writingResponse.l3_authorized_for_request ? "本次已授权 L3 证据" : "仅使用可出网证据"}</span>
                    <span>{writingResponse.sources.length} 条原页依据</span>
                  </div>
                  <div className="writingPersistenceBar">
                    <div>
                      <b>创作记录</b>
                      <small>最近一次自动保存；另可长期保存 {writingDrafts.saved_count}/{writingDrafts.max_saved} 条</small>
                    </div>
                    <button
                      type="button"
                      className="writingSaveButton"
                      disabled={writingDraftBusy === "save" || writingDrafts.saved_count >= writingDrafts.max_saved}
                      onClick={() => void handleSaveWritingDraft()}
                    >{writingDraftBusy === "save" ? "保存中…" : "保存草稿"}</button>
                    <button type="button" className="writingDownloadButton" onClick={handleDownloadWritingDraft}>
                      下载 Markdown
                    </button>
                  </div>
                  {writingDrafts.saved_count >= writingDrafts.max_saved && (
                    <p className="writingLimitNotice">已达到 5 条保存上限。删除一条旧记录后即可继续保存；最近一次创作仍会自动保存。</p>
                  )}
                  {writingDraftView === "preview" ? (
                    <article className="writingPreview">
                      <MarkdownDraft content={writingDraftText} />
                    </article>
                  ) : (
                    <textarea
                      className="writingEditor"
                      value={writingDraftText}
                      onChange={(event) => {
                        setWritingDraftText(event.target.value);
                        if (writingActiveDraftKind === "latest") setWritingLatestEditPending(true);
                      }}
                      aria-label="编辑初稿原文"
                    />
                  )}
                  <div className="writingSources">
                    <strong>引用资料（{writingResponse.sources.length}）</strong>
                    {writingResponse.sources.map((source, index) => (
                      <article key={`${source.document_id}-${source.page}`}>
                        <span>S{index + 1}</span>
                        <div>
                          <b>{source.title}</b>
                          <small>{source.version} · 第 {source.page} 页 · {categoryNames[source.domain] || source.domain}</small>
                        </div>
                        <button
                          type="button"
                          disabled={previewBusy === `${source.document_id}-${source.page}`}
                          onClick={() => void handlePreview(source.document_id, source.page)}
                        >{previewBusy === `${source.document_id}-${source.page}` ? "打开中…" : "查看原页"}</button>
                      </article>
                    ))}
                  </div>
                  <p className="proposalNotice">{writingResponse.notice}</p>
                </>
              )}
              <section className="writingDraftLibrary" aria-label="已保存的创作">
                  <div className="writingDraftLibraryHeader">
                    <div><p className="eyebrow">SAVED WRITING</p><h3>已保存的创作</h3></div>
                    <span>{writingDrafts.saved_count}/{writingDrafts.max_saved}</span>
                  </div>
                  {writingDraftMessage && <p className="writingDraftMessage" role="status">{writingDraftMessage}</p>}
                  <div className="writingDraftRows">
                    {writingDrafts.saved.length === 0 && (
                      <p className="writingDraftEmpty">还没有长期保存的创作。生成后点击“保存草稿”，最多可保留 5 条。</p>
                    )}
                    {writingDrafts.saved.map((record) => (
                      <article key={record.id}>
                        <button
                          type="button"
                          className="writingDraftRestore"
                          onClick={() => restoreWritingDraft(record, `已恢复“${record.title}”，可以继续编辑或下载。`)}
                        >
                          <b>{record.title || "未命名创作"}</b>
                          <small>{new Date(record.updated_at || record.created_at).toLocaleString("zh-CN", { hour12: false })}</small>
                        </button>
                        <button
                          type="button"
                          className="writingDraftDelete"
                          disabled={writingDraftBusy === `delete-${record.id}`}
                          onClick={() => void handleDeleteWritingDraft(record.id)}
                          aria-label={`删除已保存创作：${record.title}`}
                        >{writingDraftBusy === `delete-${record.id}` ? "删除中…" : "删除"}</button>
                      </article>
                    ))}
                  </div>
              </section>
            </section>
          </section>
        )}

        {ADVANCED_GOVERNANCE_ENABLED && active === "知识进化" && ["founder", "knowledge_admin"].includes(user.role) && (
          <section className="evolutionLayout">
            <section className="panel evolutionControl">
              <PanelTitle eyebrow="CONTROLLED EVOLUTION" title="维护资料" />
              <div className="noticeBar warning">
                <strong>受控进化</strong>
                <span>系统按周期发现变化并保存候选；审批、变更计划和正式版本发布彼此独立，任何一步都不会自动发布。</span>
              </div>
              {evolutionMessage && (
                <div className="noticeBar successNotice">
                  <strong>操作完成</strong><span>{evolutionMessage}</span>
                </div>
              )}

              {user.role === "founder" && (
                <details className="evolutionAdminBlock" open={evolutionArtifacts.length === 0}>
                  <summary>登记当前公司介绍</summary>
                  <form className="evolutionForm" onSubmit={handleRegisterEvolutionArtifact}>
                    <label className="full">
                      维护资料名称
                      <input name="name" defaultValue="京奥电竞公司介绍" required />
                    </label>
                    <label className="full">
                      已正式发布的当前版本
                      <select name="current_document_id" required defaultValue="">
                        <option value="" disabled>选择当前公司介绍</option>
                        {evolutionBaselines.map((document) => (
                          <option value={document.id} key={document.id}>
                            {document.title} · {document.version} · {confidentialityLabel(document.confidentiality)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      使用范围
                      <select name="audience" defaultValue="external">
                        <option value="external">对外资料</option>
                        <option value="internal">仅内部使用</option>
                      </select>
                    </label>
                    <label>
                      复核周期
                      <select name="review_cadence_days" defaultValue="90">
                        <option value="30">每 30 天</option>
                        <option value="60">每 60 天</option>
                        <option value="90">每 90 天</option>
                        <option value="180">每 180 天</option>
                      </select>
                    </label>
                    <label className="full">
                      当前资料截止日
                      <input name="cutoff_date" type="date" required />
                    </label>
                    <button className="primaryButton" disabled={evolutionActionBusy === "register" || evolutionBaselines.length === 0}>
                      {evolutionActionBusy === "register" ? "登记中…" : "登记维护资料"}
                    </button>
                  </form>
                  {evolutionBaselines.length === 0 && (
                    <p className="evolutionHint">请先在“入库审核”中把公司介绍确认定稿并独立发布为当前版本。</p>
                  )}
                </details>
              )}

              <div className="artifactList">
                <strong>已登记资料</strong>
                {evolutionArtifacts.map((artifact) => (
                  <button
                    type="button"
                    key={artifact.id}
                    className={selectedEvolutionArtifact?.id === artifact.id ? "active" : ""}
                    onClick={() => void openEvolutionArtifact(artifact.id)}
                    disabled={evolutionActionBusy === `open-${artifact.id}`}
                  >
                    <span>
                      <b>{artifact.name}</b>
                      <small>{artifact.audience === "external" ? "对外" : "内部"} · {confidentialityLabel(artifact.confidentiality)} · 截止 {artifact.cutoff_date}</small>
                    </span>
                    <em>{artifact.next_review_at <= SHANGHAI_TODAY ? "待复核" : artifact.next_review_at}</em>
                  </button>
                ))}
                {evolutionArtifacts.length === 0 && <p className="emptyRows">尚未登记维护资料</p>}
              </div>

              {selectedEvolutionArtifact && (
                <section className="artifactControlCard">
                  <div>
                    <span>当前基线</span>
                    <strong>{selectedEvolutionArtifact.current_document?.title || "资料中未找到"}</strong>
                    <small>{selectedEvolutionArtifact.current_document?.version} · 截止 {selectedEvolutionArtifact.cutoff_date}</small>
                  </div>
                  <form className="evolutionForm compactEvolutionForm" onSubmit={handleStartEvolutionReview}>
                    <label className="full">
                      本次复核到
                      <input name="reviewed_through" type="date" defaultValue={SHANGHAI_TODAY} required />
                    </label>
                    <button className="primaryButton" disabled={evolutionActionBusy === "start-review" || ["open", "plan_ready"].includes(evolutionRun?.status || "")}>
                      {evolutionActionBusy === "start-review" ? "核对证据中…" : "启动定期复核"}
                    </button>
                  </form>

                  {user.role === "founder" && (
                    <details className="baselineUpdate">
                      <summary>新版本已发布？更新维护基线</summary>
                      <form className="evolutionForm compactEvolutionForm" onSubmit={handleEvolutionBaselineUpdate}>
                        <label className="full">
                          正式发布的新版本
                          <select name="current_document_id" required defaultValue="">
                            <option value="" disabled>选择直接替代当前版本的文档</option>
                            {evolutionBaselines
                              .filter((document) => document.supersedes_document_id === selectedEvolutionArtifact.current_document?.id)
                              .map((document) => (
                                <option value={document.id} key={document.id}>{document.title} · {document.version}</option>
                              ))}
                          </select>
                        </label>
                        <label className="full">新资料截止日<input name="cutoff_date" type="date" required /></label>
                        <label className="full">输入确认语<input name="confirmation" placeholder="确认更新维护资料基线" required /></label>
                        <button className="primaryButton" disabled={evolutionActionBusy === "baseline"}>确认更新基线</button>
                      </form>
                    </details>
                  )}
                </section>
              )}

              <details className="evolutionAdminBlock quickDigestBlock">
                <summary>临时变化检查（不保存）</summary>
                <form className="evolutionForm" onSubmit={handleEvolutionDigest}>
                  <input type="hidden" name="artifact" value="company_profile" />
                  <label>使用范围<select name="audience" defaultValue="external"><option value="external">对外</option><option value="internal">内部</option></select></label>
                  <label>当前截止日<input name="cutoff_date" type="date" defaultValue={selectedEvolutionArtifact?.cutoff_date || "2026-02-28"} required /></label>
                  <label className="full">检查到<input name="reviewed_through" type="date" defaultValue={SHANGHAI_TODAY} required /></label>
                  <button className="secondaryButton" disabled={evolutionBusy}>{evolutionBusy ? "检查中…" : "临时检查"}</button>
                </form>
                {evolutionDigest && <p className="evolutionHint">发现 {evolutionDigest.candidates.length} 项候选；此结果未保存，请使用上方“启动定期复核”进入正式流程。</p>}
              </details>
              <div className="evolutionRules">
                <span>当前有效证据</span><span>原件哈希复验</span><span>创始人逐项审批</span><span>复核不改截止日</span>
              </div>
            </section>

            <section className="panel evolutionResult">
              {!selectedEvolutionArtifact ? (
                <div className="emptyState evolutionEmpty">
                  <b>↻</b>
                  <h3>选择一项维护资料</h3>
                  <p>登记现行公司介绍后，系统会按周期保存带页码的更新候选。</p>
                </div>
              ) : !evolutionRun ? (
                <div className="emptyState evolutionEmpty">
                  <b>✓</b>
                  <h3>{selectedEvolutionArtifact.name}</h3>
                  <p>当前截止 {selectedEvolutionArtifact.cutoff_date}，下次计划复核 {selectedEvolutionArtifact.next_review_at}。尚无复核批次。</p>
                </div>
              ) : (
                <>
                  <div className="evolutionHeader">
                    <div>
                      <p className="eyebrow">PERSISTED REVIEW</p>
                      <h2>{selectedEvolutionArtifact.name} · 复核批次</h2>
                      <small>{evolutionRun.cutoff_date} 之后至 {evolutionRun.reviewed_through}</small>
                    </div>
                    <b>{evolutionRunStatusLabel(evolutionRun.status)}</b>
                  </div>
                  <div className="evolutionStats">
                    <span><small>证据合格</small><strong>{evolutionRun.summary.eligible_count}</strong></span>
                    <span><small>已保存候选</small><strong>{evolutionRun.summary.persisted_candidate_count}</strong></span>
                    <span><small>待披露审批</small><strong>{evolutionRun.summary.blocked_count}</strong></span>
                    <span><small>资料冲突</small><strong>{evolutionRun.summary.conflict_count}</strong></span>
                  </div>
                  <div className="evolutionNext">
                    <strong>下一步</strong>
                    <p>{evolutionRun.change_plan?.plan.next_action || evolutionRun.summary.next_action}</p>
                  </div>
                  <div className="evolutionCandidates">
                    {evolutionRun.candidates.map((candidate) => (
                      <article className={`evolutionCandidate ${candidate.classification}`} key={candidate.id}>
                        <header>
                          <div>
                            <span>{candidate.target_section}</span>
                            <strong>{candidate.primary_source.project.name}</strong>
                            <small>{roleNames[candidate.primary_source.role] || candidate.primary_source.role} · {candidate.primary_source.effective_at}</small>
                          </div>
                          <div className="evolutionScore">
                            <b>{candidate.score}</b>
                            <small>{evolutionClassLabel(candidate)}</small>
                          </div>
                        </header>
                        <div className={`candidateDecisionState ${candidate.review_status}`}>
                          {evolutionDecisionLabel(candidate.review_status, candidate.disclosure_status)}
                        </div>
                        <p className="evolutionExcerpt">{candidate.primary_source.excerpt || "资料中未找到可显示的摘要"}</p>
                        <div className="evolutionSource">
                          <div>
                            <strong>{candidate.primary_source.title}</strong>
                            <small>{candidate.primary_source.version} · 第 {candidate.primary_source.page || "—"} 页 · {confidentialityLabel(candidate.primary_source.confidentiality)}</small>
                          </div>
                          {candidate.primary_source.page && (
                            <button
                              type="button"
                              className="previewLink"
                              disabled={previewBusy === `${candidate.primary_source.document_id}-${candidate.primary_source.page}`}
                              onClick={() => handlePreview(candidate.primary_source.document_id, candidate.primary_source.page || 1)}
                            >
                              {previewBusy === `${candidate.primary_source.document_id}-${candidate.primary_source.page}` ? "打开中…" : "查看原页"}
                            </button>
                          )}
                        </div>
                        {candidate.hard_gate_failures.length > 0 && (
                          <div className="evolutionBlocker">
                            {candidate.hard_gate_failures.map(evolutionGateLabel).join("；")}
                          </div>
                        )}
                        <p className="evolutionReason">{candidate.reason_new}</p>
                        {user.role === "founder" && evolutionRun.status === "open" && ["pending", "deferred"].includes(candidate.review_status) && candidate.classification !== "conflict" && (
                          <form className="candidateDecisionForm" onSubmit={(event) => void handleEvolutionDecision(event, candidate)}>
                            <label>
                              确认语
                              <input
                                name="confirmation"
                                placeholder={selectedEvolutionArtifact.audience === "external" ? "确认纳入并允许对外披露" : "确认纳入变更计划"}
                                required
                              />
                            </label>
                            <label>审批备注（可选）<input name="note" /></label>
                            <div>
                              <button type="submit" name="decision" value="approve" disabled={evolutionActionBusy === `candidate-${candidate.id}`}>纳入</button>
                              <button
                                type="submit"
                                name="decision"
                                value="reject"
                                className="dangerButton"
                                disabled={evolutionActionBusy === `candidate-${candidate.id}`}
                              >不纳入</button>
                            </div>
                            <small>纳入请按提示输入；不纳入请输入“确认不纳入”。</small>
                          </form>
                        )}
                      </article>
                    ))}
                    {evolutionRun.candidates.length === 0 && (
                      <div className="emptyRows">本周期没有合格的变化候选</div>
                    )}
                  </div>

                  {evolutionRun.change_plan && (
                    <section className="changePlanBox">
                      <div><strong>逐项变更计划</strong><span>{evolutionRun.change_plan.plan.accepted_count} 项 · 尚未发布</span></div>
                      {evolutionRun.change_plan.plan.changes.map((change) => (
                        <article key={change.candidate_id}>
                          <b>{change.action} · {change.target_section}</b>
                          <p>{change.proposed_content || "资料中未找到可显示摘要"}</p>
                          <small>{change.evidence.primary_source.title} · 第 {change.evidence.primary_source.page || "—"} 页</small>
                        </article>
                      ))}
                    </section>
                  )}

                  {user.role === "founder" && evolutionRun.status === "open" && (
                    <form className="evolutionGateForm" onSubmit={handleEvolutionPlan}>
                      <strong>冻结审批并生成变更计划</strong>
                      <p>存在冲突或未决的重要候选时，服务端会拒绝此操作。</p>
                      <input name="confirmation" placeholder="确认生成变更计划" required />
                      <button disabled={evolutionActionBusy === "change-plan"}>生成变更计划</button>
                    </form>
                  )}
                  {user.role === "founder" && ["open", "plan_ready"].includes(evolutionRun.status) && (
                    <form className="evolutionGateForm closeGate" onSubmit={handleCloseEvolutionReview}>
                      <strong>完成本次复核</strong>
                      <p>只记录复核时间并安排下一次复核，不会改变资料截止日。</p>
                      <input name="confirmation" placeholder="确认完成本次复核" required />
                      <button disabled={evolutionActionBusy === "close-review"}>完成复核</button>
                    </form>
                  )}
                </>
              )}
            </section>
          </section>
        )}

        {active === "入库审核" && (
          <section className="panel pagePanel">
            <PanelTitle
              eyebrow="INGESTION REVIEW"
              title="待审核资料"
              action={user.role === "founder"
                ? (inboxScanBusy ? "扫描中…" : "扫描待审核目录")
                : undefined}
              onAction={user.role === "founder" ? () => {
                if (!inboxScanBusy) void handleScanInbox();
              } : undefined}
            />
            <div className="noticeBar warning">
              <strong>内容文档需要确认</strong>
              <span>PPT、Word、Excel、PDF 和文本资料经预览确认后进入历史知识检索；图片、视频、音频等素材已自动入库，不出现在这里。</span>
            </div>
            {reviewMessage && (
              <div className="noticeBar successNotice">
                <strong>操作完成</strong><span>{reviewMessage}</span>
              </div>
            )}
            {user.role === "founder" && inboxIssues.length > 0 && (
              <section className="inboxIssues">
                <div className="inboxIssuesHeader">
                  <div>
                    <strong>待审核目录问题</strong>
                    <small>只显示相对路径；不会在日志或页面暴露 NAS 根路径。</small>
                  </div>
                  <div className="inboxIssuesHeaderActions">
                    <button
                      type="button"
                      className="secondaryButton"
                      disabled={inboxScanBusy}
                      onClick={() => void handleScanInbox()}
                    >
                      {inboxScanBusy ? "扫描中…" : "重新扫描"}
                    </button>
                    <b>{inboxIssues.length}</b>
                  </div>
                </div>
                {inboxIssues.map((issue) => (
                  <article key={issue.id}>
                    <div>
                      <strong>{issue.relative_path}</strong>
                      <small>{issue.message}</small>
                    </div>
                    <div className="inboxIssueActions">
                      <span>{issue.status === "deferred" ? "等待稳定" : "需处理"}</span>
                      <button
                        type="button"
                        className="secondaryButton"
                        disabled={Boolean(inboxIssueBusy)}
                        onClick={() => void handleIgnoreInboxIssue(issue)}
                      >
                        {inboxIssueBusy === issue.id ? "处理中…" : "忽略此文件"}
                      </button>
                    </div>
                  </article>
                ))}
              </section>
            )}
            {batchReviewCandidateIds.length > 0 && (
              <div className="batchReviewBar">
                <div>
                  <strong>批量审核 · 共 {batchReviewCandidateIds.length} 份</strong>
                  <span>
                    当前有 {batchEligibleReviewIds.length} 份可直接确认。L1、L2、L3 支持批量确认或拒绝；L4、L5必须逐份处理。
                  </span>
                </div>
                <div>
                  <button
                    type="button"
                    className="secondaryButton"
                    disabled={batchReviewCandidateIds.length === 0}
                    onClick={() => setSelectedReviewIds(
                      batchReviewCandidateIds.length > 0
                      && selectedReviewIds.length === batchReviewCandidateIds.length
                        ? []
                        : batchReviewCandidateIds,
                    )}
                  >
                    {batchReviewCandidateIds.length > 0
                    && selectedReviewIds.length === batchReviewCandidateIds.length
                      ? "取消全选"
                      : `全选待审核（${batchReviewCandidateIds.length}）`}
                  </button>
                  <button
                    type="button"
                    className="primaryButton"
                    disabled={
                      selectedReviewIds.filter((id) => batchEligibleReviewIds.includes(id)).length === 0
                      || reviewBusy === "batch-confirm"
                      || reviewBusy === "batch-reject"
                    }
                    onClick={() => void handleBatchConfirm()}
                  >
                    {reviewBusy === "batch-confirm"
                      ? "批量确认中…"
                      : `确认可入库（${selectedReviewIds.filter((id) => batchEligibleReviewIds.includes(id)).length}）`}
                  </button>
                  <button
                    type="button"
                    className="dangerSecondary"
                    disabled={selectedReviewIds.length === 0 || Boolean(reviewBusy)}
                    onClick={() => void handleBatchReject()}
                  >
                    {reviewBusy === "batch-reject"
                      ? "批量拒绝中…"
                      : `拒绝所选（${selectedReviewIds.length}）`}
                  </button>
                </div>
              </div>
            )}
            <div className="reviewCards">
              {reviewQueue.map((item) => (
                <article className="reviewCard" key={item.document_id}>
                  <header className="reviewCardHeader">
                    <div className="reviewIdentity">
                      {batchReviewCandidateIds.includes(item.document_id) && (
                        <label className="reviewSelect" title="加入批量处理">
                          <input
                            type="checkbox"
                            checked={selectedReviewIds.includes(item.document_id)}
                            onChange={(event) => setSelectedReviewIds((current) => (
                              event.target.checked
                                ? Array.from(new Set([...current, item.document_id]))
                                : current.filter((id) => id !== item.document_id)
                            ))}
                          />
                          <span />
                        </label>
                      )}
                      <div>
                        <strong>{item.title}</strong>
                        <small>{item.project} · {categoryNames[item.domain] || item.domain}</small>
                      </div>
                    </div>
                    <div className="reviewBadges">
                      <b className="levelBadge">{confidentialityLabel(item.confidentiality)}</b>
                      <b className="candidateBadge">{item.review_state}</b>
                    </div>
                  </header>

                  <div className="reviewFacts">
                    <span><small>年份</small><b>{item.year || "待确认"}</b></span>
                    <span><small>文档角色</small><b>{roleNames[item.role] || item.role}</b></span>
                    <span title={item.uploader_username ? `系统账号：${item.uploader_username}` : undefined}>
                      <small>上传人</small>
                      <b>
                        {item.upload_source === "web" ? "JAOS" : "NAS"}
                        {` · ${item.uploader_name}`}
                        {item.upload_source === "web" && item.uploader_username
                          ? `（${item.uploader_username}）`
                          : ""}
                      </b>
                    </span>
                    <span>
                      <small>解析</small>
                      <b className={item.issue ? "issue" : "success"}>
                        {item.issue || `${item.page_count} 页 · ${item.extracted_chunk_count} 块`}
                      </b>
                    </span>
                  </div>

                  <div className="reviewActions">
                    {item.preview_available ? (
                      <button
                        type="button"
                        className="previewLink"
                        disabled={previewBusy === `${item.document_id}-1`}
                        onClick={() => handlePreview(item.document_id)}
                      >
                        {previewBusy === `${item.document_id}-1` ? "打开中…" : "预览内容"}
                      </button>
                    ) : (
                      <small>{item.confirm_blockers[0] || "不可预览"}</small>
                    )}
                    {item.knowledge_status === "candidate" ? (
                      <>
                        <button
                          type="button"
                          className="primaryButton"
                          disabled={!item.confirm_eligible || reviewBusy === `confirm-${item.document_id}`}
                          title={item.confirm_blockers.join("；")}
                          onClick={() => void handleConfirmReview(item)}
                        >
                          {reviewBusy === `confirm-${item.document_id}` ? "确认中…" : "确认入库"}
                        </button>
                        <button
                          type="button"
                          className="dangerSecondary"
                          disabled={Boolean(reviewBusy)}
                          onClick={() => void handleRejectReview(item)}
                        >
                          {reviewBusy === `reject-${item.document_id}` ? "拒绝中…" : "拒绝入库"}
                        </button>
                        <button
                          type="button"
                          className="secondaryButton"
                          onClick={() => setReviewEditing(
                            reviewEditing === item.document_id ? "" : item.document_id,
                          )}
                        >
                          {reviewEditing === item.document_id
                            ? "收起信息"
                            : "修改信息"}
                        </button>
                      </>
                    ) : (
                      <b className="success">已确认入库</b>
                    )}
                  </div>

                  {item.pending_proposal && (
                    <section className="pendingProposal">
                      <div className="pendingProposalTitle">
                        <div>
                          <span>待采用的信息修改</span>
                          <small>提交人：{item.pending_proposal.submitted_by}</small>
                        </div>
                        <b>确认入库时一并采用</b>
                      </div>
                      <dl>
                        <div><dt>项目</dt><dd>{item.pending_proposal.project_name}</dd></div>
                        <div><dt>客户</dt><dd>{item.pending_proposal.client || "未填写"}</dd></div>
                        <div><dt>年份</dt><dd>{item.pending_proposal.year || "未填写"}</dd></div>
                        <div><dt>资料分类</dt><dd>{categoryNames[item.pending_proposal.domain] || item.pending_proposal.domain}</dd></div>
                        <div><dt>角色</dt><dd>{roleNames[item.pending_proposal.document_role] || item.pending_proposal.document_role}</dd></div>
                        <div><dt>版本</dt><dd>{item.pending_proposal.version}</dd></div>
                        <div><dt>密级</dt><dd>{confidentialityLabel(item.pending_proposal.confidentiality)}</dd></div>
                        <div><dt>定稿</dt><dd>{item.pending_proposal.is_final ? "是" : "否"}</dd></div>
                      </dl>
                      {item.pending_proposal.note && (
                        <p className="reviewNote">说明：{item.pending_proposal.note}</p>
                      )}

                      <p className="reviewWaiting">如内容和以上信息无误，直接点击“确认入库”；无需输入确认短语。</p>
                    </section>
                  )}

                  {user.role === "founder" && item.role === "company_profile" && !item.pending_proposal && (
                    <section
                      className={`publicationPanel ${
                        item.publication_eligible ? "eligible" : "blocked"
                      }`}
                    >
                      <div className="publicationTitle">
                        <div>
                          <span>发布为当前版本</span>
                          <small>
                            这是独立于元数据确认的事实发布动作，发布后员工查询“当前/最新”时才会使用。
                          </small>
                        </div>
                        <b>{item.publication_eligible ? "可发布" : "暂不可发布"}</b>
                      </div>

                      {item.publication_blockers.length > 0 && (
                        <ul className="publicationBlockers">
                          {item.publication_blockers.map((blocker) => (
                            <li key={blocker}>{blocker}</li>
                          ))}
                        </ul>
                      )}

                      {item.publication_eligible && (
                        <>
                          <div className="replacementScope">
                            <strong>本次版本替代范围</strong>
                            {item.replacement_candidates.length > 0 ? (
                              item.replacement_candidates.map((candidate) => (
                                <article key={candidate.document_id}>
                                  <div>
                                    <span>{candidate.title}</span>
                                    <small>
                                      {candidate.project} · {candidate.version}
                                    </small>
                                  </div>
                                  <b>转为历史</b>
                                </article>
                              ))
                            ) : (
                              <p>未发现同一资料系列的当前版本；本次为首次发布。</p>
                            )}
                          </div>
                          <form
                            className="publicationForm"
                            onSubmit={(event) => handlePublishReview(event, item)}
                          >
                            <label>
                              发布说明（可选）
                              <input
                                name="note"
                                maxLength={500}
                                placeholder="例如：2026年7月公司介绍定稿"
                              />
                            </label>
                            <label>
                              输入“确认发布为当前版本”
                              <input
                                name="confirmation"
                                required
                                pattern="确认发布为当前版本"
                                autoComplete="off"
                                placeholder="确认发布为当前版本"
                              />
                            </label>
                            <button
                              className="primaryButton"
                              disabled={
                                reviewBusy === `publish-${item.document_id}`
                              }
                            >
                              {reviewBusy === `publish-${item.document_id}`
                                ? "发布中…"
                                : "确认发布"}
                            </button>
                          </form>
                        </>
                      )}
                    </section>
                  )}

                  {item.knowledge_status === "candidate" && reviewEditing === item.document_id && (
                    <form
                      key={`${item.document_id}-${item.pending_proposal?.id || "new"}`}
                      className="reviewForm"
                      onSubmit={(event) => handleReviewProposal(event, item.document_id)}
                    >
                      <label>项目名称
                        <input
                          name="project_name"
                          required
                          defaultValue={item.pending_proposal?.project_name || item.project}
                        />
                      </label>
                      <label>客户
                        <input
                          name="client"
                          defaultValue={item.pending_proposal?.client || item.client || ""}
                          placeholder="无客户则留空"
                        />
                      </label>
                      <label>年份
                        <input
                          name="year"
                          type="number"
                          min="2000"
                          max="2100"
                          defaultValue={item.pending_proposal?.year || item.year || ""}
                        />
                      </label>
                      <label>资料分类
                        <select
                          name="domain"
                          defaultValue={item.pending_proposal?.domain || item.domain}
                        >
                          {activeCategories.map((category) => (
                            <option key={category.key} value={category.key}>{category.name}</option>
                            ))}
                        </select>
                      </label>
                      <label>文档角色
                        <select
                          name="document_role"
                          defaultValue={item.pending_proposal?.document_role || item.role}
                        >
                          {Object.entries(roleNames)
                            .filter(([value]) => (
                              user.role !== "department_owner"
                              || value !== "company_profile"
                            ))
                            .map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                      </label>
                      <label>版本
                        <input
                          name="version"
                          required
                          defaultValue={item.pending_proposal?.version || item.version}
                          placeholder="例如 v1.0 / 2026-07"
                        />
                      </label>
                      <label>密级
                        <select
                          name="confidentiality"
                          defaultValue={
                            item.pending_proposal?.confidentiality
                            || item.confidentiality
                          }
                        >
                          <option value="L1">{confidentialityLabel("L1")}</option>
                          <option value="L2">{confidentialityLabel("L2")}</option>
                          {user.role !== "department_owner" && (
                            <>
                              <option value="L3">{confidentialityLabel("L3")}</option>
                              <option value="L4">{confidentialityLabel("L4")}</option>
                              {user.confidentiality_ceiling === "L5" && (
                                <option value="L5">{confidentialityLabel("L5")}</option>
                              )}
                            </>
                          )}
                        </select>
                      </label>
                      <label className="reviewCheckbox">
                        <input
                          name="is_final"
                          type="checkbox"
                          defaultChecked={
                            item.pending_proposal?.is_final ?? item.is_final
                          }
                        />
                        已核对为定稿
                      </label>
                      <label className="reviewWide">核对说明
                        <textarea
                          name="note"
                          rows={3}
                          defaultValue={item.pending_proposal?.note || ""}
                          placeholder="可填写资料说明；不要填写密码或密钥。"
                        />
                      </label>
                      <div className="reviewFormFooter">
                        <span>保存后，点击“确认入库”时一并采用。</span>
                        <button
                          className="primaryButton"
                          disabled={reviewBusy === `proposal-${item.document_id}`}
                        >
                          {reviewBusy === `proposal-${item.document_id}`
                            ? "保存中…"
                            : "保存信息"}
                        </button>
                      </div>
                    </form>
                  )}
                </article>
              ))}
              {reviewQueue.length === 0 && (
                <div className="noEvidence">当前账号没有可处理的候选资料。</div>
              )}
            </div>
          </section>
        )}

        {active === "资料治理" && ["founder", "knowledge_admin"].includes(user.role) && (
          <section className="panel pagePanel governancePage">
            <PanelTitle eyebrow="CONFIDENTIALITY GOVERNANCE" title="资料密级治理" />
            <div className="noticeBar governanceNotice">
              <strong>AI本地初筛，您最终确认</strong>
              <span>分类只在京奥NAS内完成，不调用外部模型。L1至L3可批量调整；合同、L4、L5、低置信度和异常资料保留人工逐份确认。每次修改都会记录原密级、调整原因和操作人。</span>
            </div>

            {governanceMessage && (
              <div className="noticeBar successNotice">
                <strong>操作完成</strong><span>{governanceMessage}</span>
              </div>
            )}

            <div className="governanceStats">
              {(["L1", "L2", "L3", "L4", "L5"] as const).map((level) => (
                <article key={level} className={`governanceStat level-${level.toLowerCase()}`}>
                  <span>{confidentialityLabel(level)}</span>
                  <strong>{governance?.counts[level] || 0}</strong>
                  <small>份已入库资料</small>
                </article>
              ))}
            </div>

            {user.role === "founder" && (
              <section className="governanceAIBox">
                <div>
                  <span className="sectionEyebrow">LOCAL AI CLASSIFICATION</span>
                  <h3>让AI先梳理一遍</h3>
                  <p>公司介绍和明确公开素材优先归为L1；普通方案与执行资料归为L2；普通报价、预算和名单归为L3。合同档案由固定目录强制为L4或L5，不参与AI自动降级。</p>
                </div>
                <div className="governanceAIActions">
                  <button
                    type="button"
                    className="secondaryButton"
                    disabled={Boolean(governanceBusy)}
                    onClick={() => void handleGovernanceAI(true)}
                  >
                    {governanceBusy === "ai-preview" ? "分析中…" : "预看AI调整范围"}
                  </button>
                  <button
                    type="button"
                    className="primaryButton"
                    disabled={Boolean(governanceBusy)}
                    onClick={() => void handleGovernanceAI(false)}
                  >
                    {governanceBusy === "ai-apply" ? "正在应用…" : "应用AI建议"}
                  </button>
                </div>
                {governanceAIReport && (
                  <div className="governanceAIReport">
                    <b>{governanceAIReport.dry_run ? "预分析完成" : "AI初筛已应用"}</b>
                    <span>共检查 {governanceAIReport.scanned_count} 份</span>
                    <span>{governanceAIReport.dry_run ? "拟调整" : "已调整"} {governanceAIReport.proposed_change_count ?? governanceAIReport.changed_count ?? 0} 份</span>
                    <span>待人工复核 {governanceAIReport.manual_review_count} 份</span>
                    {Object.entries(governanceAIReport.proposed_counts || governanceAIReport.changed_counts || {}).map(([level, count]) => (
                      <span key={level}>{level}：{count} 份</span>
                    ))}
                  </div>
                )}
              </section>
            )}

            <form className="governanceFilters" onSubmit={handleGovernanceFilter}>
              <label>
                搜索文件或项目
                <input
                  value={governanceQuery}
                  onChange={(event) => setGovernanceQuery(event.target.value)}
                  placeholder="输入文件名或项目名"
                />
              </label>
              <label>
                资料分类
                <select value={governanceDomain} onChange={(event) => setGovernanceDomain(event.target.value)}>
                  <option value="">全部分类</option>
                  {activeCategories.map((category) => (
                    <option key={category.key} value={category.key}>{category.name}</option>
                  ))}
                </select>
              </label>
              <label>
                当前密级
                <select value={governanceLevel} onChange={(event) => setGovernanceLevel(event.target.value)}>
                  <option value="">全部密级</option>
                  {(["L1", "L2", "L3", "L4", "L5"] as const).map((level) => (
                    <option key={level} value={level}>{confidentialityLabel(level)}</option>
                  ))}
                </select>
              </label>
              <label>
                文档角色
                <select value={governanceRole} onChange={(event) => setGovernanceRole(event.target.value)}>
                  <option value="">全部角色</option>
                  {Object.entries(roleNames).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
              <label className="governanceManualFilter">
                <input
                  type="checkbox"
                  checked={governanceManualOnly}
                  onChange={(event) => setGovernanceManualOnly(event.target.checked)}
                />
                只看AI建议复核的资料
              </label>
              <button className="secondaryButton" disabled={governanceBusy === "filter"}>
                {governanceBusy === "filter" ? "筛选中…" : "筛选资料"}
              </button>
            </form>

            <section className="governanceBatchBar">
              <div>
                <strong>已选 {governanceSelected.length} 份</strong>
                <button
                  type="button"
                  className="textButton"
                  onClick={() => {
                    const selectable = (governance?.items || [])
                      .filter((item) => user.role === "founder" || !["L4", "L5"].includes(item.confidentiality))
                      .map((item) => item.document_id);
                    setGovernanceSelected(
                      governanceSelected.length === selectable.length ? [] : selectable,
                    );
                  }}
                >
                  {governanceSelected.length > 0 ? "取消选择" : "选择本页"}
                </button>
              </div>
              <label>
                调整为
                <select value={governanceTarget} onChange={(event) => setGovernanceTarget(event.target.value)}>
                  <option value="L1">{confidentialityLabel("L1")}</option>
                  <option value="L2">{confidentialityLabel("L2")}</option>
                  <option value="L3">{confidentialityLabel("L3")}</option>
                  {user.role === "founder" && <option value="L4">{confidentialityLabel("L4")}（仅单份）</option>}
                  {user.role === "founder" && <option value="L5">{confidentialityLabel("L5")}（仅单份）</option>}
                </select>
              </label>
              <label className="governanceReason">
                调整原因
                <input
                  value={governanceReason}
                  onChange={(event) => setGovernanceReason(event.target.value)}
                  maxLength={500}
                  placeholder="说明为什么调整"
                />
              </label>
              <button
                type="button"
                className="primaryButton"
                disabled={governanceSelected.length === 0 || governanceBusy === "batch"}
                onClick={() => void handleGovernanceBatch()}
              >
                {governanceBusy === "batch" ? "调整中…" : "确认调整密级"}
              </button>
            </section>

            <div className="governanceList">
              {(governance?.items || []).map((item) => {
                const selectable = user.role === "founder" || !["L4", "L5"].includes(item.confidentiality);
                return (
                  <article className="governanceCard" key={item.document_id}>
                    <label className="governanceSelect" title={selectable ? "选择资料" : "L4/L5资料只能由创始人调整"}>
                      <input
                        type="checkbox"
                        disabled={!selectable}
                        checked={governanceSelected.includes(item.document_id)}
                        onChange={(event) => setGovernanceSelected((current) => (
                          event.target.checked
                            ? Array.from(new Set([...current, item.document_id]))
                            : current.filter((id) => id !== item.document_id)
                        ))}
                      />
                    </label>
                    <div className="governanceCardBody">
                      <header>
                        <div>
                          <strong>{item.title}</strong>
                          <small>{item.project}</small>
                        </div>
                        <div className="governanceBadges">
                          <b className={`governanceLevelBadge level-${item.confidentiality.toLowerCase()}`}>
                            当前：{confidentialityLabel(item.confidentiality)}
                          </b>
                          {item.ai_suggestion.needs_review && <b className="reviewNeededBadge">建议复核</b>}
                        </div>
                      </header>
                      <div className="governanceMeta">
                        <span><small>分类</small><b>{categoryNames[item.domain] || item.domain}</b></span>
                        <span><small>角色</small><b>{roleNames[item.role] || item.role}</b></span>
                        <span><small>状态</small><b>{item.knowledge_status}</b></span>
                        <span><small>页数</small><b>{item.page_count || "—"}</b></span>
                      </div>
                      <div className="governanceSuggestion">
                        <div>
                          <span>AI建议：<b>{confidentialityLabel(item.ai_suggestion.level)}</b></span>
                          <small>置信度：{item.ai_suggestion.confidence === "high" ? "高" : item.ai_suggestion.confidence === "medium" ? "中" : "低"}</small>
                        </div>
                        <p>{item.ai_suggestion.reason}</p>
                        {item.preview_available && (
                          <button
                            type="button"
                            className="previewLink"
                            disabled={previewBusy === `${item.document_id}-1`}
                            onClick={() => handlePreview(item.document_id)}
                          >{previewBusy === `${item.document_id}-1` ? "打开中…" : "查看原文件"}</button>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
              {governance && governance.items.length === 0 && (
                <div className="noEvidence">没有符合当前筛选条件的资料。</div>
              )}
            </div>

            {governance && governance.total > governance.limit && (
              <div className="governancePagination">
                <button
                  type="button"
                  className="secondaryButton"
                  disabled={governance.offset === 0 || Boolean(governanceBusy)}
                  onClick={() => void refreshGovernance(Math.max(0, governance.offset - governance.limit))}
                >上一页</button>
                <span>第 {Math.floor(governance.offset / governance.limit) + 1} 页 · 共 {governance.total} 份</span>
                <button
                  type="button"
                  className="secondaryButton"
                  disabled={governance.offset + governance.limit >= governance.total || Boolean(governanceBusy)}
                  onClick={() => void refreshGovernance(governance.offset + governance.limit)}
                >下一页</button>
              </div>
            )}
          </section>
        )}

        {active === "账号管理" && user.role === "founder" && (
          <section className="accountLayout">
            <section className="panel categoryManage">
              <PanelTitle eyebrow="CUSTOM CATEGORIES" title="资料分类" />
              <p>这里决定上传、项目归档和员工权限中可选的分类。名称可以随时修改；停用后历史资料和引用仍会保留。</p>
              <form className="categoryCreateForm" onSubmit={handleCreateCategory}>
                <input name="name" required maxLength={80} placeholder="例如：AI 游戏、校园合作、品牌商务" />
                <button className="primaryButton" disabled={categoryBusy === "create"}>
                  {categoryBusy === "create" ? "添加中…" : "新增分类"}
                </button>
              </form>
              <div className="categoryRows">
                {categories.map((category) => (
                  <form
                    key={category.id}
                    className={!category.active ? "inactive" : ""}
                    onSubmit={(event) => handleCategoryName(event, category)}
                  >
                    <input name="name" required defaultValue={category.name} aria-label="资料分类名称" />
                    <small>{category.active ? "上传与归档可选" : "已停用，历史资料保留"}</small>
                    <button disabled={categoryBusy === category.id}>保存名称</button>
                    <button
                      type="button"
                      className="dangerButton"
                      disabled={categoryBusy === category.id}
                      onClick={() => void handleCategoryActive(category)}
                    >{category.active ? "停用" : "重新启用"}</button>
                  </form>
                ))}
              </div>
            </section>
            <section className="panel accountCreate">
              <PanelTitle eyebrow="LOCAL ACCOUNT" title="创建试点账号" />
              <p>初始密码至少 8 位。教培角色固定为 L1，可使用星曜教培项目模块；其他资料仍按密级和角色授权。</p>
              <form className="accountCreateForm" onSubmit={handleCreateAccount}>
                <label>登录账号<input name="username" required minLength={3} placeholder="例如 employee01" /></label>
                <label>员工姓名<input name="display_name" required placeholder="姓名或内部称呼" /></label>
                <label>初始密码<input name="password" type="password" required minLength={8} autoComplete="new-password" /></label>
                <AccountRoleFields />
                <button className="primaryButton" disabled={accountBusy === "create"}>
                  {accountBusy === "create" ? "创建中…" : "创建账号"}
                </button>
              </form>
            </section>
            <section className="panel accountList">
              <PanelTitle eyebrow="ACCESS CONTROL" title={`本地账号（${accounts.length}）`} />
              <p>所有账号都可以调整角色、密级、状态和密码；为避免系统失去管理员，最后一个启用的管理账号必须先安排另一个管理账号后才能停用或降级。</p>
              <div className="accountRows">
                {accounts.map((account) => (
                  <article key={account.id} className={!account.active ? "inactive" : ""}>
                    <div className="accountIdentity">
                      <div className="avatar">{account.display_name.slice(0, 1)}</div>
                      <div>
                        <strong>{account.display_name}</strong>
                        <small>{account.username} · {userRoleNames[account.organization_role] || account.organization_role}</small>
                      </div>
                      <b>{account.active ? "启用" : "停用"}</b>
                    </div>
                    <>
                        <form className="accountPolicyForm" onSubmit={(event) => handleAccountPolicy(event, account.id)}>
                          <AccountRoleFields key={`${account.id}-${account.organization_role}-${account.confidentiality_ceiling}`} initialRole={account.organization_role} initialCeiling={account.confidentiality_ceiling} />
                          <button disabled={accountBusy === account.id}>保存权限</button>
                          <button
                            type="button"
                            className="dangerButton"
                            disabled={accountBusy === account.id}
                            onClick={() => handleAccountActive(account)}
                          >
                            {account.active ? "停用" : "重新启用"}
                          </button>
                        </form>
                        <form className="accountPasswordForm" onSubmit={(event) => handleResetPassword(event, account.id)}>
                          <input
                            name="password"
                            type="password"
                            minLength={8}
                            required
                            placeholder="输入不少于8位的新密码"
                            autoComplete="new-password"
                          />
                          <button disabled={accountBusy === `password-${account.id}`}>重置密码</button>
                        </form>
                    </>
                  </article>
                ))}
              </div>
            </section>
          </section>
        )}

        {active === "系统状态" && ["founder", "knowledge_admin"].includes(user.role) && (
          <section className="operationsLayout">
            <section className="panel operationsOverview">
              <PanelTitle
                eyebrow="SYSTEM OPERATIONS"
                title="系统运行状态"
                action="立即刷新"
                onAction={() => void handleRefreshOperations()}
              />
              <div className={`operationsSummary ${operations?.status || "warning"}`}>
                <span className="operationsPulse" />
                <div>
                  <strong>{
                    operations?.status === "ok"
                      ? "系统运行正常"
                      : operations?.status === "critical"
                      ? "存在需要立即处理的异常"
                      : "系统可用，但有项目需要关注"
                  }</strong>
                  <small>
                    最近检查：{
                      operations?.generated_at
                        ? new Date(operations.generated_at).toLocaleString("zh-CN")
                        : "尚未完成"
                    }
                  </small>
                </div>
              </div>
              <div className="operationCards">
                <OperationCard label="数据库" component={operations?.components.database} />
                <OperationCard label="数据盘" component={operations?.components.storage} />
                <OperationCard label="内存" component={operations?.components.memory} />
                <OperationCard label="每日备份" component={operations?.components.backup} />
                <OperationCard label="第二物理备份" component={operations?.components.offsite_backup} />
                <OperationCard label="模型网关" component={operations?.components.gateway} />
                <OperationCard label="待审核扫描" component={operations?.components.ingestion} />
                <OperationCard label="原件完整性" component={operations?.components.source_integrity} />
              </div>
              {ADVANCED_GOVERNANCE_ENABLED && (<>
              <div className="evaluationBox">
                <div>
                  <span>TECHNICAL BASELINE</span>
                  <strong>
                    {operations?.components.evaluation?.technical_case_count || 0} / 150 项技术探针
                  </strong>
                  <small>
                    页码引用 {
                      Math.round(
                        (operations?.components.evaluation?.metrics?.page_citation_accuracy || 0) * 100,
                      )
                    }% · 拒答 {
                      Math.round(
                        (operations?.components.evaluation?.metrics?.refusal_accuracy || 0) * 100,
                      )
                    }% · 权限泄露 {
                      operations?.components.evaluation?.metrics?.permission_leak_count ?? "—"
                    } · P95 {
                      operations?.components.evaluation?.metrics?.retrieval_p95_ms ?? "—"
                    }ms
                  </small>
                  <small>
                    业务金标 {
                      operations?.components.evaluation?.business_gold_total || 0
                    } / 150；需业务负责人确认，技术探针不能替代。
                  </small>
                  <small>
                    5 人并发 {
                      operations?.components.evaluation?.concurrency_status === "passed"
                        ? "已通过"
                        : operations?.components.evaluation?.concurrency_status === "failed"
                        ? "未通过"
                        : "待运行"
                    } · {
                      operations?.components.evaluation?.concurrency_request_count || 0
                    } 次请求 · P95 {
                      operations?.components.evaluation?.concurrency_p95_ms ?? "—"
                    }ms · 错误 {
                      operations?.components.evaluation?.concurrency_error_count ?? "—"
                    }
                  </small>
                </div>
                <div className="evaluationActions">
                  <button
                    type="button"
                    onClick={() => void handleRunEvaluation()}
                    disabled={evaluationBusy || concurrencyBusy}
                  >
                    {evaluationBusy ? "正在运行…" : "运行技术评测"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleRunConcurrency()}
                    disabled={evaluationBusy || concurrencyBusy || sourceReconcileBusy}
                  >
                    {concurrencyBusy ? "正在压测…" : "运行5人并发"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleReconcileSources()}
                    disabled={evaluationBusy || concurrencyBusy || sourceReconcileBusy}
                  >
                    {sourceReconcileBusy ? "正在核验…" : "核验原件"}
                  </button>
                </div>
              </div>
              <section className="businessGoldPanel">
                <div className="businessGoldHeader">
                  <div>
                    <span>BUSINESS GOLD SET</span>
                    <strong>业务金标题库</strong>
                    <small>
                      已批准 {businessGold?.approved || 0} / {businessGold?.target || 150}，
                      待确认 {businessGold?.pending || 0}；草稿不会进入评测。
                    </small>
                  </div>
                  {businessGold?.invalid ? (
                    <b className="dangerText">发现 {businessGold.invalid} 条格式异常</b>
                  ) : null}
                  <button
                    type="button"
                    className="goldGenerateButton"
                    onClick={() => void handleGenerateBusinessGold()}
                    disabled={businessGoldBusy}
                  >
                    {businessGoldBusy ? "正在处理…" : "从真实资料生成150道候选题"}
                  </button>
                </div>

                <p className="goldQualitySummary">
                  已具备标准答案和关键点 {businessGold?.quality_ready || 0} 道。候选题只保存为草稿，必须人工核对后才能批准。
                </p>

                <form className="businessGoldCreate" onSubmit={handleCreateBusinessGold}>
                  <label className="goldQuestion">
                    <span>业务问题</span>
                    <input name="question" minLength={5} maxLength={1000} required placeholder="例如：京奥电竞当前公司介绍中列出的核心业务有哪些？" />
                  </label>
                  <label>
                    <span>分类</span>
                    <input name="category" defaultValue="business_fact" maxLength={80} required />
                  </label>
                  <label>
                    <span>预期类型</span>
                    <select name="expected_type" defaultValue="source">
                      <option value="source">命中正式来源</option>
                      <option value="refusal">资料中未找到</option>
                      <option value="no_leak">低权限无泄露</option>
                    </select>
                  </label>
                  <label className="goldSource">
                    <span>正式来源</span>
                    <select name="document_id" defaultValue="">
                      <option value="">请选择来源资料</option>
                      {businessGoldSources.map((source) => (
                        <option key={source.document_id} value={source.document_id}>
                          {source.project} · {source.title} · {source.version} · {source.page_count}页
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>页码</span>
                    <input name="page" type="number" min={1} defaultValue={1} />
                  </label>
                  <label>
                    <span>资料范围</span>
                    <select name="scope" defaultValue="auto">
                      <option value="auto">自动</option>
                      <option value="current">当前资料</option>
                      <option value="history">历史案例</option>
                      <option value="all">全部正式资料</option>
                    </select>
                  </label>
                  <label>
                    <span>检索方式</span>
                    <select name="retrieval" defaultValue="exact">
                      <option value="exact">确定性检索</option>
                      <option value="auto">自动</option>
                      <option value="hybrid">混合检索</option>
                      <option value="semantic">语义检索</option>
                    </select>
                  </label>
                  <label className="goldLongField">
                    <span>标准答案（命中来源题必填）</span>
                    <textarea name="reference_answer" rows={4} placeholder="写出可接受的标准答案；必须以选定正式资料为依据。" />
                  </label>
                  <label className="goldLongField">
                    <span>答案关键点（每行一个，至少一项）</span>
                    <textarea name="key_points" rows={4} placeholder={"例如：覆盖5个业务领域\n例如：2026年6月更新"} />
                  </label>
                  <label className="goldLongField">
                    <span>禁用说法（每行一个，可选）</span>
                    <textarea name="forbidden_claims" rows={3} placeholder="例如：把历史项目描述为当前公司最新情况" />
                  </label>
                  <button type="submit" disabled={businessGoldBusy}>
                    保存为待确认草稿
                  </button>
                </form>

                <details className="businessGoldBulk">
                  <summary>批量导入 JSON 数组 / JSONL</summary>
                  <p>导入始终写入草稿并撤销同 ID 的旧批准状态，避免修改后的题目沿用历史批准。</p>
                  <textarea
                    value={businessGoldBulk}
                    onChange={(event) => setBusinessGoldBulk(event.target.value)}
                    placeholder='[{"id":"company-fact-001","question":"……","category":"business_fact","expected":{"document_id":"正式文档ID","page":1}}]'
                  />
                  <button type="button" onClick={() => void handleImportBusinessGold()} disabled={businessGoldBusy || !businessGoldBulk.trim()}>
                    导入为待确认草稿
                  </button>
                </details>

                {businessGoldEditing && (
                  <form className="businessGoldEditor" onSubmit={handleEditBusinessGold}>
                    <div className="businessGoldEditorHead">
                      <strong>核对并修改候选题</strong>
                      <button type="button" onClick={() => setBusinessGoldEditing(null)}>取消</button>
                    </div>
                    <label>
                      <span>业务问题</span>
                      <textarea name="question" rows={3} required defaultValue={businessGoldEditing.question} />
                    </label>
                    {businessGoldEditing.expected.document_id ? (
                      <>
                        <label>
                          <span>标准答案</span>
                          <textarea name="reference_answer" rows={7} required defaultValue={businessGoldEditing.expected.reference_answer || ""} />
                        </label>
                        <label>
                          <span>答案关键点（每行一个，至少一项）</span>
                          <textarea name="key_points" rows={4} required defaultValue={(businessGoldEditing.expected.key_points || []).join("\n")} />
                        </label>
                        <label>
                          <span>禁用说法（每行一个，可选）</span>
                          <textarea name="forbidden_claims" rows={3} defaultValue={(businessGoldEditing.expected.forbidden_claims || []).join("\n")} />
                        </label>
                      </>
                    ) : null}
                    <button type="submit" disabled={businessGoldBusy}>保存修改</button>
                  </form>
                )}

                <div className="businessGoldCases">
                  {(businessGold?.cases || []).length ? (businessGold?.cases || []).map((item) => (
                    <label key={item.id} className={item.approved ? "approved" : "pending"}>
                      <input
                        type="checkbox"
                        disabled={item.approved || user?.role !== "founder"}
                        checked={businessGoldSelected.includes(item.id)}
                        onChange={(event) => setBusinessGoldSelected((current) => (
                          event.target.checked
                            ? [...current, item.id]
                            : current.filter((id) => id !== item.id)
                        ))}
                      />
                      <span>
                        <strong>{item.question}</strong>
                        <small>
                          {item.category} · {item.scope} · {item.retrieval} · {
                            item.expected.document_id
                              ? `来源 ${item.expected.document_id.slice(0, 8)}… 第${item.expected.page || 1}页`
                              : item.expected.expect_refusal
                                ? "应明确拒答"
                                : "低权限无泄露"
                          }
                        </small>
                        {item.expected.document_id ? (
                          <small className="goldAnswerSummary">
                            标准答案：{item.expected.reference_answer || "未填写"}<br />
                            关键点：{(item.expected.key_points || []).join("；") || "未填写"}<br />
                            禁用说法：{(item.expected.forbidden_claims || []).join("；") || "无"}
                          </small>
                        ) : null}
                      </span>
                      <span className="goldCaseActions">
                        <b>{item.approved ? "已批准" : "待确认"}</b>
                        {!item.approved ? (
                          <button type="button" onClick={(event) => { event.preventDefault(); setBusinessGoldEditing(item); }}>编辑内容</button>
                        ) : null}
                      </span>
                    </label>
                  )) : (
                    <p className="emptyGold">尚无业务金标。先由业务负责人填写真实问题和正式来源，再单独批准。</p>
                  )}
                </div>

                {user?.role === "founder" && (
                  <form className="businessGoldApprove" onSubmit={handleApproveBusinessGold}>
                    <label>
                      <span>核对说明</span>
                      <input name="owner_note" minLength={4} maxLength={500} required placeholder="已逐题核对问题、预期和正式资料来源" />
                    </label>
                    <label>
                      <span>确认口令</span>
                      <input name="confirmation" required placeholder="输入：确认批准业务金标" />
                    </label>
                    <button type="submit" disabled={businessGoldBusy || !businessGoldSelected.length}>
                      批准所选 {businessGoldSelected.length || 0} 题
                    </button>
                  </form>
                )}
                {businessGoldMessage && <p className="successNote">{businessGoldMessage}</p>}
              </section>
              </>)}
            </section>
            <section className="panel operationsAdvice">
              <PanelTitle eyebrow="ACTION LIST" title="处理建议" />
              <div className="adviceList">
                {(operations?.recommendations || ["正在生成运行建议…"]).map((item, index) => (
                  <article key={item}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <p>{item}</p>
                  </article>
                ))}
              </div>
              <div className="thresholdBox">
                <strong>当前告警口径</strong>
                <p>
                  磁盘达到 {operations?.thresholds.disk_warning_percent ?? 80}% 提醒、
                  {operations?.thresholds.disk_critical_percent ?? 90}% 严重；
                  内存达到 {operations?.thresholds.memory_warning_percent ?? 80}% 提醒、
                  {operations?.thresholds.memory_critical_percent ?? 90}% 严重。
                </p>
                <p>公开健康接口不返回容量、路径、模型名称等内部详情。</p>
              </div>
            </section>
          </section>
        )}

        <footer>
          <span>京奥AI智能运营系统 · JAOS</span>
          <span>{status?.policy_version} · {status?.database}</span>
        </footer>
      </section>
      <nav className="mobileTabbar" aria-label="手机端主导航">
        {mobilePrimaryTabs.map((item) => (
          <button
            type="button"
            key={item.name}
            className={active === item.name ? "active" : ""}
            aria-current={active === item.name ? "page" : undefined}
            onClick={() => navigateToTab(item.name)}
          >
            <span className="mobileTabIcon" aria-hidden="true">{item.icon}</span>
            <span>{item.name === "AI资料检索" ? "资料检索" : item.name}</span>
          </button>
        ))}
        <button
          type="button"
          className={mobileMenuOpen || mobileMoreActive ? "active" : ""}
          aria-expanded={mobileMenuOpen}
          aria-controls="mobile-more-sheet"
          onClick={() => setMobileMenuOpen(true)}
        >
          <span className="mobileTabIcon" aria-hidden="true">•••</span>
          <span>更多</span>
        </button>
      </nav>
      {mobileMenuOpen && (
        <div
          className="mobileMenuBackdrop"
          role="presentation"
          onMouseDown={() => setMobileMenuOpen(false)}
        >
          <section
            id="mobile-more-sheet"
            className="mobileMenuSheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mobile-more-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="mobileMenuHandle" aria-hidden="true" />
            <header className="mobileMenuHeader">
              <div>
                <p className="eyebrow">JAOS MOBILE</p>
                <h2 id="mobile-more-title">更多功能</h2>
              </div>
              <button type="button" aria-label="关闭更多功能" onClick={() => setMobileMenuOpen(false)}>×</button>
            </header>
            <div className="mobileMenuUser">
              <div className="avatar" aria-hidden="true">{user.display_name.slice(0, 1)}</div>
              <div>
                <strong>{user.display_name}</strong>
                <small>{userRoleNames[user.organization_role] || user.organization_role} · {confidentialityLabel(user.confidentiality_ceiling)}</small>
              </div>
            </div>
            <nav className="mobileMenuModules" aria-label="更多功能列表">
              {mobileMoreTabs.map((item) => (
                <Fragment key={item.name}>
                  <button
                    type="button"
                    className={active === item.name ? "active" : ""}
                    aria-current={active === item.name ? "page" : undefined}
                    onClick={() => navigateToTab(item.name)}
                  >
                    <span className="navIcon" aria-hidden="true">{item.icon}</span>
                    <span>{item.name}</span>
                    {item.name === "入库审核" && reviewQueue.length > 0 && <b>{reviewQueue.length}</b>}
                  </button>
                  {item.name === "财务分析" && financeEntities.length > 0 && (
                    <div className="mobileFinanceEntities" aria-label="财务公司账套">
                      {financeEntities.map((entity) => (
                        <button
                          type="button"
                          className={active === "财务分析" && selectedFinanceEntityId === entity.id ? "active" : ""}
                          onClick={() => {
                            handleFinanceEntitySelect(entity.id);
                            setMobileMenuOpen(false);
                          }}
                          key={entity.id}
                        >
                          <span>{entity.display_name}</span>
                          <small>{entity.business_name}</small>
                        </button>
                      ))}
                    </div>
                  )}
                </Fragment>
              ))}
            </nav>
            <div className="mobileMenuActions">
              <button
                type="button"
                onClick={() => {
                  setMobileMenuOpen(false);
                  setShowPasswordForm(true);
                }}
              >修改密码</button>
              <button type="button" className="danger" onClick={() => void handleLogout()}>退出登录</button>
            </div>
          </section>
        </div>
      )}
      {showPasswordForm && (
        <div
          className="modalBackdrop"
          role="presentation"
          onMouseDown={() => setShowPasswordForm(false)}
        >
          <section
            className="passwordModal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="password-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button type="button" className="modalClose" onClick={() => setShowPasswordForm(false)}>×</button>
            <p className="eyebrow">ACCOUNT SECURITY</p>
            <h2 id="password-title">修改我的密码</h2>
            <p>修改后所有已登录会话都会失效，需要重新登录。</p>
            <form onSubmit={handleOwnPassword}>
              <label>当前密码<input name="current_password" type="password" required autoComplete="current-password" /></label>
              <label>新密码<input name="new_password" type="password" required minLength={8} autoComplete="new-password" /></label>
              <button className="primaryButton" disabled={accountBusy === "own-password"}>确认修改</button>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}

function financeOptionalMoney(value: MoneyValue | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : formatMoney(value);
}

function financeShare(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  const percentage = numeric <= 1 ? numeric * 100 : numeric;
  return `${percentage.toFixed(1)}%`;
}

function financeDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("zh-CN");
}

function financeTransferReason(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    exact_cross_entity_account: "集团公司银行账号精确匹配",
    exact_same_entity_account: "同公司账户之间划转",
    exact_entity_alias: "集团公司名称或别名精确匹配",
    exact_cross_entity_alias: "集团公司名称精确匹配",
    exact_same_entity_alias: "同公司名称精确匹配",
    similar_group_entity_name: "集团公司名称相似匹配，需财务确认",
    masked_group_account_match: "集团账户尾号匹配，需财务确认",
    manual_finance_review: "财务人工确认",
  };
  if (!value) return "依据公司账户与往来单位匹配";
  return labels[value] || value;
}

function FinanceReceivablesPayablesPanel({
  dashboard,
  canEdit,
  busy,
  onCreate,
  onUpdate,
}: {
  dashboard: FinanceDashboard | null;
  canEdit: boolean;
  busy: string;
  onCreate: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onUpdate: (event: FormEvent<HTMLFormElement>, itemId: string) => Promise<void>;
}) {
  const empty: FinanceReceivablePayableSummary = { total: 0, count: 0, items: [] };
  const receivable = dashboard?.receivables_payables?.receivable || empty;
  const payable = dashboard?.receivables_payables?.payable || empty;

  const renderItem = (item: FinanceReceivablePayableItem) => (
    <article className={`financeObligationItem${item.overdue ? " overdue" : ""}`} key={`${item.source}-${item.id}`}>
      <header>
        <div>
          <span>{item.source === "project" ? "项目经理填报" : item.source === "education" ? "星曜教培同步" : "财务补充"}</span>
          <strong>{item.project_no ? `${item.project_no} · ${item.project_name || "未命名项目"}` : item.counterparty || "非项目事项"}</strong>
        </div>
        <b>{formatMoney(item.outstanding_amount)}</b>
      </header>
      <dl>
        <div><dt>计划日期</dt><dd>{item.due_date}{item.overdue ? " · 已逾期" : ""}</dd></div>
        <div><dt>应收/应付</dt><dd>{formatMoney(item.amount)}</dd></div>
        <div><dt>已收/已付</dt><dd>{formatMoney(item.actual_amount)}</dd></div>
      </dl>
      {item.counterparty && item.project_no && <p>对方：{item.counterparty}</p>}
      {item.note && <p>{item.note}</p>}
      {canEdit && item.source === "finance" && (
        <details className="financeObligationEdit">
          <summary>编辑非项目记录</summary>
          <form onSubmit={(event) => void onUpdate(event, item.id)}>
            <select name="direction" defaultValue={item.direction}><option value="receivable">应收款</option><option value="payable">应付款</option></select>
            <input name="due_date" type="date" defaultValue={item.due_date} required />
            <input name="amount" type="number" min="0.01" step="0.01" defaultValue={Number(item.amount)} required />
            <input name="actual_amount" type="number" min="0" step="0.01" defaultValue={Number(item.actual_amount)} required />
            <input name="counterparty" defaultValue={item.counterparty || ""} placeholder="对方单位" />
            <input name="note" defaultValue={item.note || ""} placeholder="说明" />
            <button disabled={busy === `receivable-payable-${item.id}`}>{busy === `receivable-payable-${item.id}` ? "保存中…" : "保存修改"}</button>
          </form>
        </details>
      )}
    </article>
  );

  const renderColumn = (
    direction: "receivable" | "payable",
    summary: FinanceReceivablePayableSummary,
  ) => (
    <section className={`financeObligationColumn ${direction}`}>
      <header>
        <div><span>{direction === "receivable" ? "RECEIVABLES" : "PAYABLES"}</span><h3>{direction === "receivable" ? "应收款" : "应付款"}</h3></div>
        <div><strong>{formatMoney(summary.total)}</strong><small>{summary.count} 条未结清明细</small></div>
      </header>
      <div className="financeObligationList">
        {summary.items.slice(0, 10).map(renderItem)}
        {!summary.items.length && <p className="mutedText">当前没有未结清记录。</p>}
      </div>
      {summary.items.length > 10 && (
        <details className="financeObligationMore">
          <summary>展开查看全部（另有 {summary.items.length - 10} 条）</summary>
          <div className="financeObligationList">{summary.items.slice(10).map(renderItem)}</div>
        </details>
      )}
    </section>
  );

  return (
    <section className="panel financeObligationsPanel" aria-labelledby="finance-obligations-title">
      <header className="financeObligationsHeader">
        <div><p>RECEIVABLES &amp; PAYABLES</p><h2 id="finance-obligations-title">应收款与应付款</h2><span>项目记录由项目经理填报后自动汇总；财务可在此补充和维护非项目事项。金额按未结清余额统计。</span></div>
        <div className="financeObligationsTotals"><article><span>应收总额</span><strong>{formatMoney(receivable.total)}</strong></article><article><span>应付总额</span><strong>{formatMoney(payable.total)}</strong></article></div>
      </header>
      <div className="financeObligationColumns">
        {renderColumn("receivable", receivable)}
        {renderColumn("payable", payable)}
      </div>
      {canEdit && (
        <details className="financeObligationCreate">
          <summary>＋ 添加非项目应收/应付</summary>
          <form onSubmit={onCreate}>
            <select name="direction" defaultValue="receivable"><option value="receivable">应收款</option><option value="payable">应付款</option></select>
            <input name="due_date" type="date" required />
            <input name="amount" type="number" min="0.01" step="0.01" placeholder="应收/应付金额" required />
            <input name="actual_amount" type="number" min="0" step="0.01" defaultValue="0" placeholder="已收/已付金额" required />
            <input name="counterparty" placeholder="对方单位" />
            <input name="note" placeholder="说明" />
            <button disabled={busy === "receivable-payable-create"}>{busy === "receivable-payable-create" ? "添加中…" : "添加到财务总览"}</button>
          </form>
        </details>
      )}
    </section>
  );
}

function FinanceHealthPanel({
  dashboard,
  transfers,
  includeInternalTransfers,
  onTransferScopeChange,
}: {
  dashboard: FinanceDashboard | null;
  transfers: FinanceInternalTransferRegistry;
  includeInternalTransfers: boolean;
  onTransferScopeChange: (include: boolean) => void;
}) {
  const snapshot = dashboard?.fund_health || dashboard?.health;
  const accountDates = (dashboard?.accounts || [])
    .map((item) => item.as_of)
    .filter(Boolean)
    .sort();
  const dataAsOf = snapshot?.data_as_of || accountDates.at(-1) || null;
  const calculatedFreshness = dataAsOf
    ? Math.max(0, Math.floor((new Date(`${SHANGHAI_TODAY}T00:00:00+08:00`).getTime() - new Date(dataAsOf).getTime()) / 86_400_000))
    : null;
  const freshnessDays = snapshot?.freshness_days ?? calculatedFreshness;
  const freshnessStatus = snapshot?.freshness_status
    || (freshnessDays === null ? "no_data" : freshnessDays <= 7 ? "fresh" : freshnessDays <= 14 ? "attention" : "stale");
  const freshnessCopy = freshnessStatus === "fresh"
    ? "数据在正常更新周期内"
    : freshnessStatus === "attention"
      ? "已超过一周，建议补充流水"
      : freshnessStatus === "stale"
        ? "数据已滞后，请尽快补传"
        : "等待首批已确认流水";
  const maximumDailyOutflow = snapshot?.maximum_daily_net_outflow?.amount;
  const maximumDailyOutflowDate = snapshot?.maximum_daily_net_outflow?.date;
  const averageFourWeekNet = snapshot?.average_weekly_net_inflow_4w?.amount;
  const fallbackIncomeTotal = Number(dashboard?.income || 0);
  const fallbackExpenseTotal = Number(dashboard?.expense || 0);
  const fallbackIncomeShare = fallbackIncomeTotal > 0
    ? (dashboard?.weekly_top_income || []).slice(0, 3).reduce((total, item) => total + Number(item.amount || 0), 0) / fallbackIncomeTotal
    : null;
  const fallbackExpenseShare = fallbackExpenseTotal > 0
    ? (dashboard?.weekly_top_expense || []).slice(0, 3).reduce((total, item) => total + Number(item.amount || 0), 0) / fallbackExpenseTotal
    : null;
  const internalTransferAmount = snapshot?.internal_transfers?.gross_amount
    ?? dashboard?.internal_transfer_summary?.confirmed_amount
    ?? transfers.confirmed_amount;

  return (
    <section className="financeHealthSection" aria-labelledby="finance-health-title">
      <header className="financeHealthHeader">
        <div>
          <p>CAPITAL HEALTH</p>
          <h2 id="finance-health-title">资金健康</h2>
          <span>以已确认银行流水计算；“收入”与“支出”均为资金口径，不等同会计收入与成本。</span>
        </div>
        <div className="financeTransferScope" role="group" aria-label="内部划转统计口径">
          <span>经营收支口径</span>
          <div>
            <button type="button" className={!includeInternalTransfers ? "active" : ""} aria-pressed={!includeInternalTransfers} onClick={() => onTransferScopeChange(false)}>剔除内部划转</button>
            <button type="button" className={includeInternalTransfers ? "active" : ""} aria-pressed={includeInternalTransfers} onClick={() => onTransferScopeChange(true)}>包含内部划转</button>
          </div>
          <small>改变收支、净流入、趋势、排行与异常口径；银行账户余额始终不受影响。</small>
        </div>
      </header>

      <div className="financeHealthGrid">
        <article className={`financeHealthFreshness ${freshnessStatus}`}>
          <span>数据截止日</span>
          <strong>{financeDate(dataAsOf)}</strong>
          <small>{freshnessDays === null ? freshnessCopy : `距今 ${freshnessDays} 天 · ${freshnessCopy}`}</small>
        </article>
        <article>
          <span>周期最低余额</span>
          <strong>{financeOptionalMoney(snapshot?.minimum_balance?.amount)}</strong>
          <small>{snapshot?.minimum_balance?.date
            ? snapshot.minimum_balance.coverage_complete
              ? `发生于 ${financeDate(snapshot.minimum_balance.date)} · 全周期账户完整覆盖`
              : `发生于 ${financeDate(snapshot.minimum_balance.date)} · 仅 ${snapshot.minimum_balance.covered_days || 0}/${snapshot.minimum_balance.total_days || 0} 日完整覆盖，自 ${financeDate(snapshot.minimum_balance.coverage_start)}`
            : "待已确认余额数据生成"}</small>
        </article>
        <article>
          <span>最大单日净流出</span>
          <strong className="financeExpenseAmount">{financeOptionalMoney(maximumDailyOutflow)}</strong>
          <small>{maximumDailyOutflowDate ? `发生于 ${financeDate(maximumDailyOutflowDate)}` : "按自然日汇总收支"}</small>
        </article>
        <article>
          <span>近 4 周平均净流入</span>
          <strong className={Number(averageFourWeekNet || 0) < 0 ? "negative" : "positive"}>{financeOptionalMoney(averageFourWeekNet)}</strong>
          <small>用于观察短期资金趋势，不是现金预测</small>
        </article>
        <article>
          <span>收入 Top 3 集中度</span>
          <strong>{financeShare(snapshot?.top3_income_concentration?.ratio ?? fallbackIncomeShare)}</strong>
          <small>前三大往来单位占同期银行收入</small>
        </article>
        <article>
          <span>支出 Top 3 集中度</span>
          <strong>{financeShare(snapshot?.top3_expense_concentration?.ratio ?? fallbackExpenseShare)}</strong>
          <small>前三大往来单位占同期银行支出</small>
        </article>
        <article>
          <span>未分类流水金额</span>
          <strong>{financeOptionalMoney(snapshot?.unclassified?.amount)}</strong>
          <small>{snapshot?.unclassified ? `${snapshot.unclassified.count} 笔 · 建议财务优先治理` : "建议财务优先治理的大额未分类流水"}</small>
        </article>
        <article className="financeHealthTransferMetric">
          <span>已确认内部划转</span>
          <strong>{financeOptionalMoney(internalTransferAmount)}</strong>
          <small>{transfers.confirmed_count || dashboard?.internal_transfer_summary?.confirmed_count || 0} 笔 · 当前经营口径{includeInternalTransfers ? "已包含" : "已剔除"}</small>
        </article>
      </div>
    </section>
  );
}

function FinanceInternalTransfersPanel({
  registry,
  canEdit,
  busy,
  onDecision,
}: {
  registry: FinanceInternalTransferRegistry;
  canEdit: boolean;
  busy: string;
  onDecision: (transferId: string, action: "confirm" | "reject" | "reset") => Promise<void>;
}) {
  const candidates = registry.items.filter((item) => item.status === "candidate");
  const confirmed = registry.items.filter((item) => item.status === "confirmed");

  const renderTransfer = (item: FinanceInternalTransfer, mode: "candidate" | "confirmed") => {
    const confidence = item.confidence === null || item.confidence === undefined
      ? null
      : (Number(item.confidence) <= 1 ? Number(item.confidence) * 100 : Number(item.confidence));
    return (
      <article className={`financeTransferItem ${item.status}`} key={item.id}>
        <header>
          <time>{financeDate(item.transaction_date)}</time>
          <b>{financeOptionalMoney(item.amount)}</b>
        </header>
        <div className="financeTransferFlow">
          <span>{item.source_entity_name || "来源公司待确认"}</span>
          <i aria-hidden="true">→</i>
          <span>{item.target_entity_name || "目标公司待确认"}</span>
        </div>
        <p>{item.summary || item.counterparty || "银行摘要未提供"}</p>
        <footer>
          <small>{item.reason ? financeTransferReason(item.reason) : confidence === null ? "依据公司账户与往来单位匹配" : `系统匹配置信度 ${confidence.toFixed(0)}%`}</small>
          {canEdit && mode === "candidate" && (
            <div className="financeTransferActions">
              <button type="button" className="secondaryTransferAction" disabled={busy === `transfer-reject-${item.id}`} onClick={() => void onDecision(item.transaction_id || item.id, "reject")}>
                {busy === `transfer-reject-${item.id}` ? "处理中…" : "不是内部划转"}
              </button>
              <button type="button" className="primaryTransferAction" disabled={busy === `transfer-confirm-${item.id}`} onClick={() => void onDecision(item.transaction_id || item.id, "confirm")}>
                {busy === `transfer-confirm-${item.id}` ? "处理中…" : "确认划转"}
              </button>
            </div>
          )}
          {canEdit && mode === "confirmed" && (
            <button type="button" className="secondaryTransferAction" disabled={busy === `transfer-reject-${item.id}`} onClick={() => void onDecision(item.transaction_id || item.id, "reject")}>
              {busy === `transfer-reject-${item.id}` ? "处理中…" : "撤销标记"}
            </button>
          )}
        </footer>
      </article>
    );
  };

  return (
    <section className="panel financeInternalTransferPanel" aria-labelledby="internal-transfer-title">
      <header className="financeTransferPanelHeader">
        <div>
          <p>GROUP TREASURY</p>
          <h2 id="internal-transfer-title">集团内部划转</h2>
          <span>识别京奥、王牌猎豹与劲腾豹跃之间的资金移动，防止集团经营收支被重复放大。</span>
        </div>
        <div className="financeTransferSummary">
          <article><span>待确认候选</span><strong>{registry.candidate_count}</strong><small>{financeOptionalMoney(registry.candidate_amount)}</small></article>
          <article><span>已确认划转</span><strong>{registry.confirmed_count}</strong><small>{financeOptionalMoney(registry.confirmed_amount)}</small></article>
        </div>
      </header>

      <div className="financeTransferColumns">
        <section>
          <div className="financeTransferListHeading"><h3>待确认候选</h3><span>财务确认后才会从经营口径剔除</span></div>
          <div className="financeTransferList">
            {candidates.slice(0, 20).map((item) => renderTransfer(item, "candidate"))}
            {!candidates.length && <div className="financeTransferEmpty"><b>✓</b><span>当前没有待确认的内部划转候选</span></div>}
          </div>
        </section>
        <section>
          <div className="financeTransferListHeading"><h3>已确认明细</h3><span>误标时可撤销并恢复为普通经营流水</span></div>
          <div className="financeTransferList">
            {confirmed.slice(0, 20).map((item) => renderTransfer(item, "confirmed"))}
            {!confirmed.length && <div className="financeTransferEmpty neutral"><b>↔</b><span>尚无已确认的集团内部划转</span></div>}
          </div>
        </section>
      </div>
    </section>
  );
}

function FinanceWorkspace({
  token,
  user,
  entity,
  entities,
  dashboard,
  periodView,
  annualYears,
  annualDashboard,
  batches,
  cashEntries,
  transfers,
  purposeCorrections,
  includeInternalTransfers,
  selectedBatch,
  transactions,
  busy,
  message,
  uploadError,
  canEditBank,
  canDeleteConfirmedBatch,
  canReviewPurposeCorrections,
  canEditCash,
  projects,
  onEntitySelect,
  onPeriodViewChange,
  onTransferScopeChange,
  onTransferDecision,
  onReceivablePayableCreate,
  onReceivablePayableUpdate,
  onUpload,
  onCashEntry,
  onSelectBatch,
  onConfirmBatch,
  onDeleteBatch,
  onUpdateTransaction,
  onPurposeCorrectionRequest,
  onPurposeCorrectionReview,
}: {
  token: string;
  user: User;
  entity: FinanceEntity;
  entities: FinanceEntity[];
  dashboard: FinanceDashboard | null;
  periodView: "realtime" | number;
  annualYears: number[];
  annualDashboard: FinanceAnnualDashboard | null;
  batches: FinanceBatch[];
  cashEntries: CashLedgerEntry[];
  transfers: FinanceInternalTransferRegistry;
  purposeCorrections: FinancePurposeCorrectionRegistry;
  includeInternalTransfers: boolean;
  selectedBatch: string;
  transactions: FinanceTransaction[];
  busy: string;
  message: string;
  uploadError: string;
  canEditBank: boolean;
  canDeleteConfirmedBatch: boolean;
  canReviewPurposeCorrections: boolean;
  canEditCash: boolean;
  projects: ManagedProject[];
  onEntitySelect: (entityId: string) => void;
  onPeriodViewChange: (view: "realtime" | number) => void;
  onTransferScopeChange: (include: boolean) => void;
  onTransferDecision: (transferId: string, action: "confirm" | "reject" | "reset") => Promise<void>;
  onReceivablePayableCreate: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onReceivablePayableUpdate: (event: FormEvent<HTMLFormElement>, itemId: string) => Promise<void>;
  onUpload: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onCashEntry: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onSelectBatch: (batchId: string) => Promise<void>;
  onConfirmBatch: (batchId: string) => Promise<void>;
  onDeleteBatch: (batch: FinanceBatch) => Promise<void>;
  onUpdateTransaction: (event: FormEvent<HTMLFormElement>, transactionId: string) => Promise<void>;
  onPurposeCorrectionRequest: (event: FormEvent<HTMLFormElement>, transactionId: string) => Promise<void>;
  onPurposeCorrectionReview: (correctionId: string, decision: "approve" | "reject") => Promise<void>;
}) {
  const chartMax = Math.max(1, ...(dashboard?.weekly || []).flatMap((item) => [Number(item.income), Number(item.expense)]));
  const selected = batches.find((item) => item.id === selectedBatch);
  const weekRange = dashboard
    ? formatChineseDateRange(dashboard.period_start, dashboard.period_end)
    : "统计周期加载中";
  const monthRange = dashboard?.previous_month
    ? formatChineseDateRange(dashboard.previous_month.period_start, dashboard.previous_month.period_end)
    : "统计周期加载中";
  const yearRange = dashboard?.current_year
    ? formatChineseDateRange(dashboard.current_year.period_start, dashboard.current_year.period_end)
    : "统计周期加载中";
  const financeHeroEntityName = entity.is_headquarters ? entity.display_name : entity.name;
  const [editingTransactionId, setEditingTransactionId] = useState("");
  const [financeView, setFinanceView] = useState<"bank" | "cash" | "cost-centers">("bank");
  const [costCenterRegistry, setCostCenterRegistry] = useState<FinanceCostCenterRegistry | null>(null);
  const [selectedCostCenter, setSelectedCostCenter] = useState("CC26A01");
  const [costCenterLedger, setCostCenterLedger] = useState<FinanceCostCenterLedger | null>(null);
  const [costCenterBusy, setCostCenterBusy] = useState(false);
  const [costCenterError, setCostCenterError] = useState("");
  const [annualSearchQuery, setAnnualSearchQuery] = useState("");
  const [annualSearchResult, setAnnualSearchResult] = useState<FinanceAnnualTransactionSearch | null>(null);
  const [annualSearchBusy, setAnnualSearchBusy] = useState(false);
  const [annualSearchError, setAnnualSearchError] = useState("");
  useEffect(() => {
    setAnnualSearchQuery("");
    setAnnualSearchResult(null);
    setAnnualSearchError("");
  }, [entity.id, periodView, includeInternalTransfers]);
  useEffect(() => {
    if (financeView === "cost-centers" && !entity.is_headquarters) setFinanceView("bank");
    if (financeView === "cash" && !entity.show_cash) setFinanceView("bank");
  }, [entity.is_headquarters, entity.show_cash, financeView]);
  useEffect(() => {
    if (financeView !== "cost-centers" || !entity.is_headquarters) return;
    let cancelled = false;
    setCostCenterBusy(true);
    setCostCenterError("");
    const params = new URLSearchParams({
      entity_id: entity.id,
      include_internal_transfers: includeInternalTransfers ? "true" : "false",
    });
    kbFetch<FinanceCostCenterRegistry>(`v1/finance/cost-centers?${params.toString()}`, {}, token)
      .then((payload) => {
        if (cancelled) return;
        setCostCenterRegistry(payload);
        setSelectedCostCenter((current) => (
          payload.items.some((item) => item.code === current)
            ? current
            : payload.items[0]?.code || "CC26A01"
        ));
      })
      .catch((cause) => {
        if (!cancelled) setCostCenterError(cause instanceof Error ? cause.message : "公司编码加载失败");
      })
      .finally(() => {
        if (!cancelled) setCostCenterBusy(false);
      });
    return () => { cancelled = true; };
  }, [entity.id, entity.is_headquarters, financeView, includeInternalTransfers, token]);
  useEffect(() => {
    if (financeView !== "cost-centers" || !entity.is_headquarters || !selectedCostCenter) return;
    let cancelled = false;
    setCostCenterBusy(true);
    setCostCenterError("");
    setCostCenterLedger(null);
    const params = new URLSearchParams({
      entity_id: entity.id,
      include_internal_transfers: includeInternalTransfers ? "true" : "false",
    });
    kbFetch<FinanceCostCenterLedger>(
      `v1/finance/cost-centers/${encodeURIComponent(selectedCostCenter)}/transactions?${params.toString()}`,
      {},
      token,
    )
      .then((payload) => { if (!cancelled) setCostCenterLedger(payload); })
      .catch((cause) => {
        if (!cancelled) setCostCenterError(cause instanceof Error ? cause.message : "编码流水加载失败");
      })
      .finally(() => { if (!cancelled) setCostCenterBusy(false); });
    return () => { cancelled = true; };
  }, [entity.id, entity.is_headquarters, financeView, includeInternalTransfers, selectedCostCenter, token]);
  const handleAnnualTransactionSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (periodView === "realtime") return;
    const query = annualSearchQuery.trim();
    if (!query) {
      setAnnualSearchError("请输入往来单位、用途、摘要、金额、日期或流水号关键字");
      return;
    }
    setAnnualSearchBusy(true);
    setAnnualSearchError("");
    try {
      const params = new URLSearchParams({
        entity_id: entity.id,
        year: String(periodView),
        q: query,
        include_internal_transfers: includeInternalTransfers ? "true" : "false",
        limit: "100",
      });
      setAnnualSearchResult(await kbFetch<FinanceAnnualTransactionSearch>(
        `v1/finance/annual-transactions/search?${params.toString()}`,
        {},
        token,
      ));
    } catch (cause) {
      setAnnualSearchResult(null);
      setAnnualSearchError(cause instanceof Error ? cause.message : "年度流水检索失败");
    } finally {
      setAnnualSearchBusy(false);
    }
  };
  const transactionProjectLabel = (item: FinanceTransaction) => {
    const linked = projects.find((project) => project.id === item.pm_project_id);
    if (linked) return `${linked.project_no} · ${linked.name}`;
    return item.project_reference || "未关联项目";
  };
  const purposeStatusLabel = (status: FinancePurposeCorrection["status"]) => ({
    pending: "待创始人复核",
    approved: "已通过",
    rejected: "已拒绝",
  })[status];
  const renderPurposeCorrectionWorkflow = (item: FinanceTransaction) => {
    const correction = item.purpose_correction;
    const isPending = correction?.status === "pending";
    return (
      <section className={`transactionPurposeWorkflow ${isPending ? "pending" : ""}`}>
        <header>
          <div><span>实际业务用途</span><strong>修正需创始人复核</strong></div>
          {correction && <b className={`purposeStatus ${correction.status}`}>{purposeStatusLabel(correction.status)}</b>}
        </header>
        <p>当前采用：{item.note || "尚未填写"}</p>
        {correction && (
          <div className="transactionPurposeDecision">
            <span>{correction.status === "pending" ? "本次申请" : "最近申请"}</span>
            <strong>{correction.proposed_purpose}</strong>
            <small>
              {correction.requested_by} · {formatShanghaiDateTime(correction.requested_at)}
              {correction.reviewed_by ? ` · ${correction.reviewed_by}已复核` : ""}
            </small>
            {correction.review_comment && <em>复核说明：{correction.review_comment}</em>}
          </div>
        )}
        {canEditBank && !isPending && (
          <form className="purposeCorrectionForm" onSubmit={(event) => onPurposeCorrectionRequest(event, item.id)}>
            <label>
              <span>修正后的实际业务用途</span>
              <textarea name="proposed_purpose" rows={3} required maxLength={1000} placeholder="写清实际收入来源或支出用途；提交后需创始人复核" />
            </label>
            <button type="submit" disabled={busy === `purpose-request-${item.id}`}>
              {busy === `purpose-request-${item.id}` ? "提交中…" : "提交创始人复核"}
            </button>
          </form>
        )}
        {isPending && <small className="purposePendingHint">复核完成前不会覆盖当前采用用途，也不会修改银行原始附言。</small>}
      </section>
    );
  };

  const entitySwitcher = (
    <section className="financeEntitySwitcher" aria-label="选择财务公司账套">
      <div className="financeEntitySwitcherCopy">
        <p>COMPANY LEDGER</p>
        <strong>{entity.display_name}</strong>
        <span>{entity.business_name}</span>
      </div>
      <div className="financeEntitySwitcherButtons" role="tablist" aria-label="公司财务账套">
        {entities.map((item) => (
          <button
            type="button"
            role="tab"
            aria-selected={item.id === entity.id}
            className={item.id === entity.id ? "active" : ""}
            onClick={() => onEntitySelect(item.id)}
            key={item.id}
          >
            <strong>{item.display_name}</strong>
            <small>{item.business_name}</small>
          </button>
        ))}
      </div>
    </section>
  );

  const periodSwitcher = (
    <section className="financePeriodSwitcher" aria-label="选择财务分析周期">
      <div>
        <span>ANALYSIS PERIOD</span>
        <strong>{periodView === "realtime" ? "实时经营总览" : `${periodView} 年度分析`}</strong>
        <small>实时页关注近期经营；年度页按自然年复盘全年银行现金流。</small>
      </div>
      <div className="financePeriodSwitcherButtons" role="tablist">
        <button type="button" role="tab" aria-selected={periodView === "realtime"} className={periodView === "realtime" ? "active" : ""} onClick={() => onPeriodViewChange("realtime")}>实时总览</button>
        {annualYears.map((year) => (
          <button type="button" role="tab" aria-selected={periodView === year} className={periodView === year ? "active" : ""} onClick={() => onPeriodViewChange(year)} key={year}>{year} 年度</button>
        ))}
        {entity.is_headquarters && <button type="button" className="costCenterMenuButton" onClick={() => setFinanceView("cost-centers")}>编码账簿</button>}
      </div>
    </section>
  );

  if (financeView === "cash" && entity.show_cash) {
    return (
      <section className="financeWorkspace offbookCashWorkspace">
        {entitySwitcher}
        <section className="financeOffbookHero">
          <div>
            <p>OFF-BOOK CASH LEDGER</p>
            <span>京奥电竞账外现金独立台账</span>
            <strong>{formatMoney(dashboard?.cash_balance ?? 0)}</strong>
            <small>L4 本地财务数据 · 与账内银行指标完全分开</small>
          </div>
          <button type="button" onClick={() => setFinanceView("bank")}>← 返回账内财务</button>
        </section>

        {message && <div className="noticeBar successNotice"><strong>操作完成</strong><span>{message}</span></div>}

        <section className={`financeCashStandaloneGrid ${canEditCash ? "editable" : "readonly"}`}>
          {canEditCash && (
            <section className="panel financeOperationCard">
              <PanelTitle eyebrow="OFF-BOOK CASH" title="登记账外现金" />
              <p>财务、叶靖波和安利园可以登记。每笔记录均保留操作人与审计时间。</p>
              <form className="businessForm" onSubmit={onCashEntry}>
                <input name="entity_id" type="hidden" value={entity.id} readOnly />
                <div className="formGrid twoColumns">
                  <label>公司主体<input name="company_name" value={entity.name} readOnly required /></label>
                  <label>现金账户<input name="cash_account" defaultValue="公司现金" required /></label>
                  <label>日期<input name="transaction_date" type="date" defaultValue={SHANGHAI_TODAY} required /></label>
                  <label>类型<select name="direction" defaultValue="expense"><option value="opening">期初余额</option><option value="income">收入</option><option value="expense">支出</option></select></label>
                  <label>金额<input name="amount" type="number" min="0.01" step="0.01" required /></label>
                  <label>分类<input name="category" defaultValue="其他" required /></label>
                  <label>关联项目<select name="pm_project_id" defaultValue=""><option value="">不关联项目</option>{projects.map((item) => <option key={item.id} value={item.id}>{item.project_no} · {item.name}</option>)}</select></label>
                </div>
                <label>说明<textarea name="note" rows={3} required placeholder="说明现金来源、用途和经手事项" /></label>
                <button className="primaryButton full" disabled={busy === "cash"}>{busy === "cash" ? "保存中…" : "登记现金记录"}</button>
              </form>
            </section>
          )}

          <section className="panel compactLedgerPanel">
            <PanelTitle eyebrow="CASH LEDGER" title="账外现金记录" />
            <div className="cashEntryList">
              {cashEntries.map((item) => (
                <article key={item.id}><span>{item.transaction_date}</span><div><strong>{item.company} · {item.category}</strong><small>{item.cash_account} · {item.note}</small></div><b className={item.direction === "expense" ? "financeExpenseAmount" : "financeIncomeAmount"}>{item.direction === "expense" ? "−" : "+"}{formatMoney(item.amount)}</b></article>
              ))}
              {!cashEntries.length && <p className="mutedText">暂无账外现金记录。</p>}
            </div>
          </section>
        </section>
      </section>
    );
  }
  if (financeView === "cost-centers" && entity.is_headquarters) {
    const groupedCostCenters = (costCenterRegistry?.items || []).reduce<Record<string, FinanceCostCenterSummary[]>>((groups, item) => {
      (groups[item.group] ||= []).push(item);
      return groups;
    }, {});
    return (
      <section className="financeWorkspace financeCostCenterWorkspace">
        {entitySwitcher}
        <section className="financeCostCenterHero">
          <div>
            <p>COST CENTRE LEDGER</p>
            <span>京奥电竞公司编码账簿</span>
            <strong>2026 年起按编码归集全部收支</strong>
            <small>选择编码即可查看该项目段的全部已确认银行收入与支出。</small>
          </div>
          <div className="financeCostCenterHeroActions">
            <button type="button" className={includeInternalTransfers ? "active" : ""} onClick={() => onTransferScopeChange(!includeInternalTransfers)}>{includeInternalTransfers ? "包含内部划转" : "剔除内部划转"}</button>
            <button type="button" onClick={() => setFinanceView("bank")}>返回财务总览</button>
          </div>
        </section>

        {costCenterError && <div className="noticeBar warningNotice"><strong>编码账簿暂不可用</strong><span>{costCenterError}</span></div>}
        <section className="financeCostCenterGroups" aria-label="公司编码菜单">
          {Object.entries(groupedCostCenters).map(([group, items]) => (
            <section className="panel financeCostCenterGroup" key={group}>
              <header><h2>{group}</h2><span>{items.length} 个编码</span></header>
              <div>
                {items.map((item) => (
                  <button
                    type="button"
                    className={selectedCostCenter === item.code ? "active" : ""}
                    onClick={() => setSelectedCostCenter(item.code)}
                    key={item.code}
                  >
                    <span><b>{item.code}</b><strong>{item.label}</strong></span>
                    <small>{item.transaction_count} 笔 · 收 {formatMoney(item.income)} · 支 {formatMoney(item.expense)}</small>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </section>

        <section className="panel financeCostCenterLedgerPanel">
          <header>
            <div><span>CODE LEDGER</span><h2>{costCenterLedger ? `${costCenterLedger.code} · ${costCenterLedger.label}` : selectedCostCenter}</h2><p>当前公司编码下的全部已确认银行流水。</p></div>
            {costCenterLedger && <b>{costCenterLedger.transaction_count} 笔</b>}
          </header>
          {costCenterLedger && (
            <>
              <section className="financeCostCenterMetrics">
                <article><span>收入</span><strong className="financeIncomeAmount">{formatMoney(costCenterLedger.income)}</strong></article>
                <article><span>支出</span><strong className="financeExpenseAmount">{formatMoney(costCenterLedger.expense)}</strong></article>
                <article><span>净额</span><strong className={Number(costCenterLedger.net) >= 0 ? "positive" : "negative"}>{formatMoney(costCenterLedger.net)}</strong></article>
              </section>
              <div className="financeCostCenterTransactions">
                {costCenterLedger.items.map((item) => {
                  const isIncome = Number(item.income) > 0;
                  return (
                    <article key={item.id}>
                      <time>{formatShanghaiDateTime(item.transacted_at)}</time>
                      <div><strong>{item.counterparty || "未识别往来单位"}</strong><p>{item.note || item.summary || "暂无用途说明"}</p><small>{item.batch_filename}{item.bank_serial ? ` · 流水号 ${item.bank_serial}` : ""}</small></div>
                      <b className={isIncome ? "financeIncomeAmount" : "financeExpenseAmount"}>{isIncome ? "+" : "−"}{formatMoney(isIncome ? item.income : item.expense)}</b>
                    </article>
                  );
                })}
                {!costCenterLedger.items.length && <div className="emptyState compact"><b>¥</b><h3>该编码暂无已确认流水</h3><p>上传、补齐编码并确认后会自动显示在这里。</p></div>}
              </div>
            </>
          )}
          {costCenterBusy && !costCenterLedger && <p className="mutedText">正在加载编码流水…</p>}
        </section>
      </section>
    );
  }
  if (periodView !== "realtime") {
    const annual = annualDashboard?.year === periodView ? annualDashboard : null;
    const maxMonthly = Math.max(
      1,
      ...(annual?.monthly || []).flatMap((item) => [Number(item.income), Number(item.expense)]),
    );
    const coverageRange = annual?.coverage.confirmed_period_start && annual.coverage.confirmed_period_end
      ? formatChineseDateRange(annual.coverage.confirmed_period_start, annual.coverage.confirmed_period_end)
      : "尚无已确认流水";
    const categoryPanel = (
      title: string,
      items: FinanceAnnualDashboard["income_categories"],
      direction: "income" | "expense",
    ) => (
      <section className="panel financeAnnualCategoryPanel">
        <header><span>{direction === "income" ? "INCOME MIX" : "EXPENSE MIX"}</span><h3>{title}</h3></header>
        <div>
          {items.slice(0, 8).map((item) => (
            <article key={item.name}>
              <div><strong>{item.name}</strong><small>{item.transaction_count} 笔 · {(Number(item.ratio) * 100).toFixed(1)}%</small></div>
              <b className={direction === "income" ? "financeIncomeAmount" : "financeExpenseAmount"}>{formatMoney(item.amount)}</b>
            </article>
          ))}
          {!items.length && <p className="mutedText">该年度暂无可分析数据。</p>}
        </div>
      </section>
    );
    return (
      <section className="financeWorkspace financeAnnualWorkspace">
        {entitySwitcher}
        {periodSwitcher}
        {!annual ? (
          <section className="panel financeAnnualLoading"><strong>{busy === "annual" ? `正在分析 ${periodView} 年度流水…` : "年度数据暂不可用"}</strong><span>年度统计仅使用已确认银行流水。</span></section>
        ) : (
          <>
            <section className="financeAnnualHero">
              <div>
                <p>ANNUAL FINANCIAL REVIEW</p>
                <span>{entity.display_name} · {periodView} 年度</span>
                <small>全年账内银行净流入</small>
                <strong className={Number(annual.net) >= 0 ? "positive" : "negative"}>{formatMoney(annual.net)}</strong>
                <em>{annual.transaction_count} 条已确认流水 · {annual.counterparty_count} 个往来单位</em>
              </div>
              <aside className={annual.coverage.data_complete ? "complete" : "attention"}>
                <span>{annual.coverage.data_complete ? "年度数据已核对" : "年度数据尚未完整"}</span>
                <b>已确认覆盖 {coverageRange}</b>
                <small>{annual.coverage.confirmed_batch_count} 个批次已确认{annual.coverage.pending_batch_count ? ` · ${annual.coverage.pending_batch_count} 个批次待确认` : " · 无待确认批次"}</small>
                {annual.coverage.pending_batches.map((item) => <i key={item.id}>{item.filename}</i>)}
              </aside>
            </section>

            {!annual.coverage.data_complete && (
              <div className="noticeBar warningNotice"><strong>当前不是完整全年口径</strong><span>待确认批次不会计入任何指标；财务确认后年度页会自动更新。</span></div>
            )}

            <section className="financeAnnualScopeBar">
              <div><strong>经营口径</strong><span>余额始终按银行原值；切换只影响收支、排行与异常。</span></div>
              <button type="button" className={includeInternalTransfers ? "active" : ""} onClick={() => onTransferScopeChange(!includeInternalTransfers)}>{includeInternalTransfers ? "当前：包含内部划转" : "当前：剔除内部划转"}</button>
            </section>

            <section className="panel financeAnnualSearchPanel" aria-labelledby="annual-transaction-search-title">
              <header>
                <div>
                  <span>ANNUAL LEDGER SEARCH</span>
                  <h2 id="annual-transaction-search-title">检索 {periodView} 年流水</h2>
                  <p>在当前公司和年度的已确认流水中，查找往来单位、用途、银行摘要、金额、日期、分类、成本中心/项目代码或流水号。</p>
                </div>
                <b>L4 · 本地确定性检索</b>
              </header>
              <form onSubmit={handleAnnualTransactionSearch}>
                <label>
                  <span className="srOnly">流水检索关键字</span>
                  <input
                    value={annualSearchQuery}
                    onChange={(event) => setAnnualSearchQuery(event.target.value)}
                    maxLength={120}
                    placeholder="例如：腾竞、场地费、Cc2508、100000、2025-06-18"
                    aria-describedby="annual-search-scope"
                  />
                </label>
                <button type="submit" disabled={annualSearchBusy}>{annualSearchBusy ? "检索中…" : "检索年度流水"}</button>
                {(annualSearchQuery || annualSearchResult) && (
                  <button
                    type="button"
                    className="clearAnnualSearch"
                    onClick={() => {
                      setAnnualSearchQuery("");
                      setAnnualSearchResult(null);
                      setAnnualSearchError("");
                    }}
                  >清空</button>
                )}
              </form>
              <small id="annual-search-scope">当前范围：{entity.display_name} · {periodView} 年 · {includeInternalTransfers ? "包含集团内部划转" : "剔除集团内部划转"} · 仅已确认流水</small>
              {annualSearchError && <div className="financeAnnualSearchError" role="alert">{annualSearchError}</div>}
              {annualSearchResult && (
                <div className="financeAnnualSearchResults">
                  <div className="financeAnnualSearchSummary">
                    <strong>找到 {annualSearchResult.total} 条流水</strong>
                    <span>关键字“{annualSearchResult.query}”{annualSearchResult.total > annualSearchResult.limit ? ` · 当前显示前 ${annualSearchResult.limit} 条` : ""}</span>
                  </div>
                  <div className="financeAnnualSearchList">
                    {annualSearchResult.items.map((item) => {
                      const isIncome = Number(item.income) > 0;
                      return (
                        <article key={item.id}>
                          <header>
                            <div>
                              <time>{formatShanghaiDateTime(item.transacted_at)}</time>
                              <strong>{item.counterparty || "未识别往来单位"}</strong>
                            </div>
                            <b className={isIncome ? "financeIncomeAmount" : "financeExpenseAmount"}>
                              {isIncome ? "收入 " : "支出 "}{formatMoney(isIncome ? item.income : item.expense)}
                            </b>
                          </header>
                          <div className="financeAnnualSearchMatchFields">
                            {item.matched_fields.map((field) => <span key={field}>命中：{field}</span>)}
                          </div>
                          <p>{item.note ? `实际用途：${item.note}` : item.summary ? `银行摘要：${item.summary}` : "暂无用途或银行摘要"}</p>
                          {item.note && item.summary && <small className="financeAnnualRawSummary">银行原始附言：{item.summary}</small>}
                          <dl>
                            <div><dt>余额</dt><dd>{item.balance === null ? "—" : formatMoney(item.balance)}</dd></div>
                            <div><dt>分类</dt><dd>{item.category || "未分类"}</dd></div>
                            <div><dt>项目代码</dt><dd>{item.project_reference || "未关联"}</dd></div>
                            <div><dt>账户</dt><dd>{item.bank_name} · {item.account}</dd></div>
                          </dl>
                          <footer>
                            <span>{item.batch_filename}{item.bank_serial ? ` · 流水号 ${item.bank_serial}` : ""}</span>
                            <button
                              type="button"
                              onClick={() => {
                                onPeriodViewChange("realtime");
                                void onSelectBatch(item.batch_id);
                              }}
                            >查看所在批次</button>
                          </footer>
                        </article>
                      );
                    })}
                    {!annualSearchResult.items.length && (
                      <div className="financeAnnualSearchEmpty"><b>未找到匹配流水</b><span>可尝试单位简称、金额（不含逗号）、日期或银行摘要中的词。</span></div>
                    )}
                  </div>
                </div>
              )}
            </section>

            <section className="financeAnnualMetricGrid">
              <article><span>全年收入</span><strong className="financeIncomeAmount">{formatMoney(annual.income)}</strong><small>{annual.income_transaction_count} 笔 · 单笔均值 {formatMoney(annual.average_income)}</small></article>
              <article><span>全年支出</span><strong className="financeExpenseAmount">{formatMoney(annual.expense)}</strong><small>{annual.expense_transaction_count} 笔 · 单笔均值 {formatMoney(annual.average_expense)}</small></article>
              <article><span>全年净流入</span><strong className={Number(annual.net) >= 0 ? "positive" : "negative"}>{formatMoney(annual.net)}</strong><small>收入减支出</small></article>
              <article><span>年末账内余额</span><strong>{formatMoney(annual.closing_balance)}</strong><small>年初 {formatMoney(annual.opening_balance)} · 变动 {formatMoney(annual.balance_change)}</small></article>
            </section>

            <section className="panel financeAnnualTrendPanel">
              <header><div><span>12-MONTH CASHFLOW</span><h2>{periodView} 年月度现金流走势</h2></div><small>只做月度分布，不重复实时页的周度分析</small></header>
              <div className="financeAnnualMonthChart">
                {annual.monthly.map((item) => (
                  <article key={item.month}>
                    <span>{item.month}月</span>
                    <div className="financeAnnualBars"><i className="income" style={{ height: `${Math.max(Number(item.income) / maxMonthly * 100, Number(item.income) ? 3 : 0)}%` }} /><i className="expense" style={{ height: `${Math.max(Number(item.expense) / maxMonthly * 100, Number(item.expense) ? 3 : 0)}%` }} /></div>
                    <b className={Number(item.net) >= 0 ? "positive" : "negative"}>{formatMoney(item.net)}</b>
                    <small>{item.transaction_count} 笔</small>
                  </article>
                ))}
              </div>
              <footer><span><i className="income" />收入</span><span><i className="expense" />支出</span></footer>
            </section>

            <section className="financeAnnualRankingGrid">
              <FinanceRankingPanel eyebrow="ANNUAL INCOME TOP 10" title="全年收入前 10 往来单位" range={`${periodView} 年`} items={annual.top_income} direction="income" emptyText="全年暂无已确认收入。" />
              <FinanceRankingPanel eyebrow="ANNUAL EXPENSE TOP 10" title="全年支出前 10 往来单位" range={`${periodView} 年`} items={annual.top_expense} direction="expense" emptyText="全年暂无已确认支出。" />
            </section>

            <section className="financeAnnualConcentrationGrid">
              <article><span>收入 Top 5 集中度</span><strong className="financeIncomeAmount">{(Number(annual.income_concentration.ratio) * 100).toFixed(1)}%</strong><small>前五单位贡献 {formatMoney(annual.income_concentration.amount)}</small></article>
              <article><span>支出 Top 5 集中度</span><strong className="financeExpenseAmount">{(Number(annual.expense_concentration.ratio) * 100).toFixed(1)}%</strong><small>前五单位占用 {formatMoney(annual.expense_concentration.amount)}</small></article>
              <article className={Number(annual.unclassified.ratio) > 0.2 ? "attention" : ""}><span>未分类流水占比</span><strong>{(Number(annual.unclassified.ratio) * 100).toFixed(1)}%</strong><small>{annual.unclassified.count} 笔 · {formatMoney(annual.unclassified.amount)}</small></article>
              <article><span>年度异常提示</span><strong>{annual.anomaly_count}</strong><small>行为变化与数据质量规则</small></article>
            </section>

            <section className="financeAnnualCategoryGrid">
              {categoryPanel("全年收入分类结构", annual.income_categories, "income")}
              {categoryPanel("全年支出分类结构", annual.expense_categories, "expense")}
            </section>

            <section className="financeAnnualRiskGrid">
              <section className="panel financeAnnualOutflowPanel">
                <header><span>LIQUIDITY PRESSURE</span><h3>单日净流出峰值</h3></header>
                <div>{annual.largest_outflow_days.slice(0, 8).map((item, index) => <article key={item.date}><b>{index + 1}</b><div><strong>{item.date}</strong><small>{item.transaction_count} 笔 · 收入 {formatMoney(item.income)}</small></div><em className="financeExpenseAmount">{formatMoney(Math.abs(Number(item.net)))}</em></article>)}{!annual.largest_outflow_days.length && <p className="mutedText">全年没有单日净流出。</p>}</div>
              </section>
              <FinanceAlertsPanel eyebrow="ANNUAL RISK & EXCEPTION" title="年度风险与异常预警" range={`${periodView} 年`} periodLabel="全年" count={annual.anomaly_count} items={annual.anomalies} onSelectBatch={onSelectBatch} />
            </section>
          </>
        )}
      </section>
    );
  }
  return (
    <section className="financeWorkspace">
      {entitySwitcher}
      {periodSwitcher}
      <section className="financeHeroPanel">
        <div className="financeHeroCopy">
          <p>JINGAO FINANCIAL COMMAND CENTER</p>
          <span>{financeHeroEntityName} · {entity.account_label}</span>
          <small>账内银行余额总览</small>
          <strong>{formatMoney(dashboard?.bank_balance ?? 0)}</strong>
          {entity.show_cash && (
            <div className="financeOffbookEntry">
              <span>账外余额 {formatMoney(dashboard?.cash_balance ?? 0)}</span>
              <button type="button" onClick={() => setFinanceView("cash")}>账外现金 →</button>
            </div>
          )}
        </div>
        <div className="financeHeroStatus">
          <span>L4 本地财务数据</span>
          <b>{dashboard?.pending_batches ? "有待确认流水" : "数据已核对"}</b>
          <small>{entity.display_name} · {user.display_name} · 上周 {weekRange}</small>
        </div>
      </section>

      <section className="financeMetricGrid">
        <article><span>账内上周收入</span><strong className="financeIncomeAmount">{formatMoney(dashboard?.income ?? 0)}</strong><small>{weekRange} · 仅银行流水</small></article>
        <article><span>账内上周支出</span><strong className="financeExpenseAmount">{formatMoney(dashboard?.expense ?? 0)}</strong><small>{weekRange} · 不含账外现金</small></article>
        <article><span>账内上周净流入</span><strong>{formatMoney(dashboard?.net ?? 0)}</strong><small>{weekRange} · 已确认口径</small></article>
      </section>

      <FinanceReceivablesPayablesPanel
        dashboard={dashboard}
        canEdit={canEditBank}
        busy={busy}
        onCreate={onReceivablePayableCreate}
        onUpdate={onReceivablePayableUpdate}
      />

      <FinanceHealthPanel
        dashboard={dashboard}
        transfers={transfers}
        includeInternalTransfers={includeInternalTransfers}
        onTransferScopeChange={onTransferScopeChange}
      />

      <FinanceInternalTransfersPanel
        registry={transfers}
        canEdit={canEditBank}
        busy={busy}
        onDecision={onTransferDecision}
      />

      <section className="financeWeeklyInsights">
        <FinanceRankingPanel
          eyebrow="WEEKLY INCOME TOP 10"
          title="上周收入前 10 公司 / 单位"
          range={weekRange}
          items={dashboard?.weekly_top_income || []}
          direction="income"
          emptyText="上周暂无已确认收入。"
        />
        <FinanceRankingPanel
          eyebrow="WEEKLY EXPENSE TOP 10"
          title="上周支出前 10 公司 / 单位"
          range={weekRange}
          items={dashboard?.weekly_top_expense || []}
          direction="expense"
          emptyText="上周暂无已确认支出。"
        />
        <FinanceAlertsPanel
          eyebrow="WEEKLY RISK & EXCEPTION"
          title="上周风险与异常预警"
          range={weekRange}
          periodLabel="上周"
          count={dashboard?.anomaly_count || 0}
          items={dashboard?.anomalies || []}
          onSelectBatch={onSelectBatch}
        />
      </section>

      <section className="financeMonthlySection">
        <header><div><p>PREVIOUS MONTH</p><h2>账内上月经营流量</h2></div><span>{monthRange}</span></header>
        <div className="financeMonthlyGrid">
          <article><span>账内上月收入</span><strong className="financeIncomeAmount">{formatMoney(dashboard?.previous_month?.income ?? 0)}</strong><small>{monthRange} · 仅银行流水</small></article>
          <article><span>账内上月支出</span><strong className="financeExpenseAmount">{formatMoney(dashboard?.previous_month?.expense ?? 0)}</strong><small>{monthRange} · 不含账外现金</small></article>
          <article><span>账内上月净流入</span><strong>{formatMoney(dashboard?.previous_month?.net ?? 0)}</strong><small>{monthRange} · 已确认口径</small></article>
        </div>
      </section>

      <section className="financeMonthlyInsights">
        <FinanceRankingPanel
          eyebrow="MONTHLY INCOME TOP 10"
          title="上月收入前 10 公司 / 单位"
          range={monthRange}
          items={dashboard?.monthly_top_income || []}
          direction="income"
          emptyText="上月暂无已确认收入。"
        />
        <FinanceRankingPanel
          eyebrow="MONTHLY EXPENSE TOP 10"
          title="上月支出前 10 公司 / 单位"
          range={monthRange}
          items={dashboard?.monthly_top_expense || []}
          direction="expense"
          emptyText="上月暂无已确认支出。"
        />
        <FinanceAlertsPanel
          eyebrow="MONTHLY RISK & EXCEPTION"
          title="上月风险与异常预警"
          range={monthRange}
          periodLabel="上月"
          count={dashboard?.monthly_anomaly_count || 0}
          items={dashboard?.monthly_anomalies || []}
          onSelectBatch={onSelectBatch}
        />
      </section>

      <section className="financeMonthlySection financeYearSection">
        <header><div><p>YEAR TO DATE</p><h2>账内本年累计经营流量</h2></div><span>{yearRange}</span></header>
        <div className="financeMonthlyGrid">
          <article><span>账内本年收入</span><strong className="financeIncomeAmount">{formatMoney(dashboard?.current_year?.income ?? 0)}</strong><small>{yearRange} · 仅银行流水</small></article>
          <article><span>账内本年支出</span><strong className="financeExpenseAmount">{formatMoney(dashboard?.current_year?.expense ?? 0)}</strong><small>{yearRange} · 不含账外现金</small></article>
          <article><span>账内本年净流入</span><strong>{formatMoney(dashboard?.current_year?.net ?? 0)}</strong><small>{yearRange} · 已确认口径</small></article>
        </div>
      </section>

      {message && <div className="noticeBar successNotice"><strong>操作完成</strong><span>{message}</span></div>}

      <section className="financeDashboardGrid">
        <section className="panel financeTrendPanel">
          <PanelTitle eyebrow="CASHFLOW TREND" title="近 26 周收支与净流入趋势" />
          <p className="financeTrendExplanation">红柱为收入，绿柱为支出；右侧显示当周净流入或净流出，不是收入金额。</p>
          {(dashboard?.weekly.length || 0) === 0 ? (
            <div className="emptyState compact"><b>¥</b><h3>等待首批银行流水</h3><p>上传并确认后自动形成周度收支趋势。</p></div>
          ) : (
            <div className="financeTrendChart">
              {dashboard?.weekly.map((item) => {
                const net = Number(item.net);
                const netDirection = net > 0 ? "inflow" : net < 0 ? "outflow" : "balanced";
                return (
                  <div className="trendRow" key={`${item.year}-${item.week}`}>
                    <span>{item.year} W{String(item.week).padStart(2, "0")}</span>
                    <div className="trendBars">
                      <i className="income" style={{ width: `${Math.max(2, Number(item.income) / chartMax * 100)}%` }} />
                      <i className="expense" style={{ width: `${Math.max(2, Number(item.expense) / chartMax * 100)}%` }} />
                    </div>
                    <div className={`trendNetValue ${netDirection}`}>
                      <small>{net > 0 ? "净流入" : net < 0 ? "净流出" : "收支平衡"}</small>
                      <b>{formatMoney(Math.abs(net))}</b>
                    </div>
                  </div>
                );
              })}
              <div className="trendLegend"><span><i className="income" />收入</span><span><i className="expense" />支出</span></div>
            </div>
          )}
        </section>
        <section className="panel financeAccountPanel">
          <PanelTitle eyebrow="LIQUIDITY" title={`${entity.display_name}银行账户余额`} />
          <div className="financeAccountList">
            {(dashboard?.accounts || []).map((item) => (
              <article key={`${item.company}-${item.bank_name}-${item.account}`}>
                <div><strong>{item.company}</strong><span>{item.bank_name} · {item.account}</span></div>
                <div><b>{formatMoney(item.balance)}</b><small>截至 {new Date(item.as_of).toLocaleDateString("zh-CN")}</small></div>
              </article>
            ))}
            {!dashboard?.accounts.length && <p className="mutedText">尚无已确认银行余额。</p>}
          </div>
        </section>
      </section>

      {canEditBank && (
        <section className="financeOperationsGrid bankOnly">
          {canEditBank && (
            <section className="panel financeOperationCard">
              <PanelTitle eyebrow="BANK STATEMENT" title="导入银行流水" />
              <p>支持 XLSX / CSV。京奥 2026 年起优先识别“项目中心号”列，也兼容手工表中的“成本中心、项目代码、项目段”等表头；每笔流水必须选择有效公司编码后才能确认。</p>
              <form className="businessForm" onSubmit={onUpload}>
                <input name="entity_id" type="hidden" value={entity.id} readOnly />
                <div className="formGrid twoColumns">
                  <label>公司主体<input name="company_name" value={entity.name} readOnly required /></label>
                  <label>开户银行<input name="bank_name" defaultValue={entity.default_bank_name} required placeholder={entity.is_headquarters ? "北京银行成寿寺支行" : "填写该公司开户银行"} /></label>
                  <label>账户名称<input name="account_name" placeholder="基本户 / 一般户" /></label>
                  <label>完整银行账号<input name="account_number" required placeholder="仅用于本地去重，页面只显示掩码" /></label>
                </div>
                <label className="fileInputCard">选择银行导出的 XLSX 或 CSV<input name="file" type="file" required accept=".xlsx,.csv" /></label>
                <button className="primaryButton full" disabled={busy === "upload"}>{busy === "upload" ? "正在解析…" : "上传并解析流水"}</button>
              </form>
              {uploadError && (
                <div className="noticeBar errorNotice financeUploadError" role="alert">
                  <strong>本次未导入</strong>
                  <span>{uploadError}</span>
                </div>
              )}
            </section>
          )}
        </section>
      )}

      <section className="panel financeLedgerPanel">
        <PanelTitle eyebrow="RECONCILIATION" title="银行流水批次" />
        <div className="noticeBar financeConfirmationNotice">
          <strong>{canEditBank ? "财务核对确认" : canDeleteConfirmedBatch ? "创始人删除权限" : "确认责任说明"}</strong>
          <span>
            {canEditBank
              ? "请在逐条核对日期、对方、收支金额和余额后确认；未确认批次可由财务删除，确认后只有创始人可以删除。"
              : canDeleteConfirmedBatch
                ? "财务负责上传和确认；已确认批次如需删除，仅创始人可操作，删除会同步影响财务分析和项目收支。"
                : "银行流水由财务负责人上传、修正并确认；管理账号查看确认结果和审计记录。"}
          </span>
        </div>
        <div className="financeBatchList">
          {batches.map((item) => (
            <article className={selectedBatch === item.id ? "active" : ""} key={item.id}>
              <button type="button" className="batchMain" onClick={() => void onSelectBatch(item.id)}>
                <strong>{item.company}</strong>
                <span>{item.bank_name} {item.account} · {item.period_start} 至 {item.period_end}</span>
                <small>{item.filename} · 上传者 {item.uploader} · {item.row_count} 条 · 去重 {item.duplicate_count} 条</small>
                {item.status === "confirmed" && (
                  <small className="financeConfirmationMeta">
                    财务确认人 {item.confirmer || "未记录"}
                    {item.confirmed_at ? ` · ${formatShanghaiDateTime(item.confirmed_at)}` : ""}
                  </small>
                )}
              </button>
              <b className={`statusPill ${item.status}`}>{item.status === "confirmed" ? "财务已确认" : "待财务确认"}</b>
              <div className="financeBatchActions">
                {canEditBank && item.status !== "confirmed" && (
                  <button type="button" className="secondaryButton" disabled={Boolean(busy)} onClick={() => void onConfirmBatch(item.id)}>确认流水</button>
                )}
                {((canEditBank && item.status !== "confirmed") || (canDeleteConfirmedBatch && item.status === "confirmed")) && (
                  <button
                    type="button"
                    className="dangerButton financeBatchDelete"
                    disabled={Boolean(busy)}
                    onClick={() => void onDeleteBatch(item)}
                  >
                    {busy === `delete-${item.id}` ? "删除中…" : item.status === "confirmed" ? "删除已确认批次" : "删除批次"}
                  </button>
                )}
              </div>
            </article>
          ))}
          {!batches.length && <p className="mutedText">尚未上传银行流水。</p>}
        </div>
      </section>

      <section className={`panel financePurposeReviewPanel ${purposeCorrections.pending_count ? "attention" : ""}`}>
        <header className="financePurposeReviewHeader">
          <div>
            <p>PURPOSE CORRECTION REVIEW</p>
            <h2>流水实际用途修正</h2>
            <span>银行原始附言永久保留；财务提交的实际用途只有创始人复核通过后才生效。</span>
          </div>
          <aside>
            <strong>{purposeCorrections.pending_count}</strong>
            <span>项待复核</span>
          </aside>
        </header>
        <div className="financePurposeReviewList">
          {purposeCorrections.items.slice(0, 20).map((correction) => {
            const isIncome = Number(correction.transaction.income) > 0;
            return (
              <article className={correction.status} key={correction.id}>
                <header>
                  <div>
                    <b className={`purposeStatus ${correction.status}`}>{purposeStatusLabel(correction.status)}</b>
                    <time>{correction.transaction.transacted_at ? formatShanghaiDateTime(correction.transaction.transacted_at) : "日期未知"}</time>
                  </div>
                  <strong className={isIncome ? "financeIncomeAmount" : "financeExpenseAmount"}>
                    {isIncome ? "收入" : "支出"} {formatMoney(isIncome ? correction.transaction.income : correction.transaction.expense)}
                  </strong>
                </header>
                <div className="financePurposeTransactionMeta">
                  <strong>{correction.transaction.counterparty || "未识别对方单位"}</strong>
                  <span>{correction.transaction.batch_filename}</span>
                  {correction.transaction.summary && <small>银行原始附言：{correction.transaction.summary}</small>}
                </div>
                <div className="financePurposeCompare">
                  <div><span>当前采用用途</span><p>{correction.previous_purpose || "尚未填写"}</p></div>
                  <i>→</i>
                  <div><span>财务申请修正为</span><p>{correction.proposed_purpose}</p></div>
                </div>
                <footer>
                  <span>
                    申请人 {correction.requested_by} · {formatShanghaiDateTime(correction.requested_at)}
                    {correction.reviewed_by ? ` · 复核人 ${correction.reviewed_by}` : ""}
                  </span>
                  {correction.review_comment && <em>复核说明：{correction.review_comment}</em>}
                  <div>
                    {correction.transaction.batch_id && (
                      <button type="button" className="secondaryButton" onClick={() => void onSelectBatch(correction.transaction.batch_id || "")}>查看所在批次</button>
                    )}
                    {canReviewPurposeCorrections && correction.status === "pending" && (
                      <>
                        <button type="button" className="purposeRejectButton" disabled={busy === `purpose-review-${correction.id}`} onClick={() => void onPurposeCorrectionReview(correction.id, "reject")}>拒绝</button>
                        <button type="button" className="purposeApproveButton" disabled={busy === `purpose-review-${correction.id}`} onClick={() => void onPurposeCorrectionReview(correction.id, "approve")}>批准并采用</button>
                      </>
                    )}
                  </div>
                </footer>
              </article>
            );
          })}
          {!purposeCorrections.items.length && (
            <div className="financePurposeReviewEmpty">
              <b>✓</b><span>当前没有用途修正申请</span>
            </div>
          )}
        </div>
      </section>

      {selected && (
        <section className="panel transactionPanel">
          <PanelTitle eyebrow="TRANSACTIONS" title={`${selected.company} · ${selected.row_count} 条流水`} />
          <div className="tableScroll desktopDataTable financeTransactionTable">
            <table className="businessTable">
              <thead><tr><th>日期</th><th>收 / 付款人及业务事由</th><th>收入</th><th>支出</th><th>余额</th><th>分类与项目</th></tr></thead>
              <tbody>
                {transactions.map((item) => (
                  <Fragment key={item.id}>
                    <tr>
                      <td className="transactionDateCell">{formatShanghaiDateTime(item.transacted_at)}</td>
                      <td className="transactionIdentityCell">
                        <strong>{item.counterparty || "—"}</strong>
                        <small className={item.note ? "transactionBusinessPurpose" : "transactionPurposeMissing"}>
                          {item.note
                            ? `业务事由：${item.note}`
                            : item.summary?.includes("网银报销")
                              ? "银行原表仅标注“网银报销”，需补充具体事由"
                              : "业务事由待补充"}
                        </small>
                        {item.purpose_correction?.status === "pending" && (
                          <small className="transactionPurposePendingBadge">用途修正待创始人复核：{item.purpose_correction.proposed_purpose}</small>
                        )}
                        {item.summary && (
                          <details className="bankRawSummary">
                            <summary>查看银行原始附言</summary>
                            <p>{item.summary}</p>
                          </details>
                        )}
                        {canEditBank && (
                          <button
                            type="button"
                            className="transactionRowEditButton"
                            onClick={() => setEditingTransactionId((current) => current === item.id ? "" : item.id)}
                          >
                            {editingTransactionId === item.id
                              ? "收起"
                              : selected.status === "confirmed" ? "分类 / 用途修正" : "核对 / 用途修正"}
                          </button>
                        )}
                      </td>
                      <td className="financeIncomeAmount">{Number(item.income) ? formatMoney(item.income) : "—"}</td>
                      <td className="financeExpenseAmount">{Number(item.expense) ? formatMoney(item.expense) : "—"}</td>
                      <td>{item.balance === null ? "—" : formatMoney(item.balance)}</td>
                      <td className="transactionClassificationCell">
                        <span>{(!item.category || item.category === "待确认") ? "未分类" : item.category}</span>
                        <small>{transactionProjectLabel(item)}</small>
                      </td>
                    </tr>
                    {editingTransactionId === item.id && canEditBank && (
                      <tr className="transactionEditorRow">
                        <td colSpan={6}>
                          <div className="transactionEditWorkflow">
                            <form
                              className="transactionEditExpanded"
                              onSubmit={async (event) => {
                                await onUpdateTransaction(event, item.id);
                                setEditingTransactionId("");
                              }}
                            >
                              <input type="hidden" name="annotation_only" value={selected.status === "confirmed" ? "true" : "false"} />
                              {selected.status !== "confirmed" && <label><span>交易日期与时间</span><input name="transacted_at" type="datetime-local" step="1" defaultValue={toShanghaiDateTimeLocal(item.transacted_at)} required /></label>}
                              {selected.status !== "confirmed" && <label><span>收 / 付款人</span><input name="counterparty" defaultValue={item.counterparty || ""} placeholder="填写银行实际收/付款人" /></label>}
                              {selected.status === "confirmed" && <p className="transactionAnnotationNotice">该流水已经确认；金额、日期、收付款人及银行原始附言不会被改动。实际用途修正须走下方创始人复核。</p>}
                              <label><span>财务分类</span><input name="category" defaultValue={item.category || "未分类"} required /></label>
                              <label className={item.project_reference_valid === false ? "invalidFinanceField" : ""}>
                                <span>公司编码 / 项目段</span>
                                {entity.is_headquarters ? (
                                  <select name="project_reference" defaultValue={item.project_reference || ""} required>
                                    <option value="">请选择公司编码</option>
                                    {item.project_reference && !COST_CENTER_OPTIONS.some(([code]) => code === item.project_reference?.toUpperCase()) && <option value={item.project_reference}>{item.project_reference}（需修正）</option>}
                                    {COST_CENTER_OPTIONS.map(([code, label]) => <option key={code} value={code}>{code} · {label}</option>)}
                                  </select>
                                ) : <input name="project_reference" defaultValue={item.project_reference || ""} placeholder="项目代码" />}
                                {item.project_reference_valid === false && <small>2026 年起京奥流水必须选择有效公司编码后才能确认。</small>}
                              </label>
                              <label><span>关联 JAOS 项目（可选）</span><select name="pm_project_id" defaultValue={item.pm_project_id || ""}><option value="">暂不关联</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.project_no} · {project.name}</option>)}</select></label>
                              {item.summary && <details className="bankRawSummary editorRawSummary"><summary>查看银行原始附言（不可修改）</summary><p>{item.summary}</p></details>}
                              <div className="transactionEditActions">
                                <button type="button" className="secondaryButton" onClick={() => setEditingTransactionId("")}>取消</button>
                                <button type="submit" disabled={busy === `transaction-${item.id}`}>{busy === `transaction-${item.id}` ? "保存中…" : "保存分类与项目"}</button>
                              </div>
                            </form>
                            {renderPurposeCorrectionWorkflow(item)}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mobileDataCards financeTransactionCards" aria-label="手机端银行流水">
            {transactions.map((item) => (
              <article className="mobileDataCard financeTransactionCard" key={item.id}>
                <header>
                  <div>
                    <time>{formatShanghaiDateTime(item.transacted_at)}</time>
                    <strong>{item.counterparty || "未识别对方单位"}</strong>
                  </div>
                  <span className={Number(item.income) ? "financeIncomeAmount" : "financeExpenseAmount"}>
                    {Number(item.income) ? `收入 ${formatMoney(item.income)}` : `支出 ${formatMoney(item.expense)}`}
                  </span>
                </header>
                <p className={item.note ? "transactionBusinessPurpose" : "transactionPurposeMissing"}>
                  {item.note
                    ? `业务事由：${item.note}`
                    : item.summary?.includes("网银报销")
                      ? "银行原表仅标注“网银报销”，需补充具体事由"
                      : "业务事由待补充"}
                </p>
                {item.purpose_correction?.status === "pending" && (
                  <p className="transactionPurposePendingBadge">用途修正待创始人复核：{item.purpose_correction.proposed_purpose}</p>
                )}
                {item.summary && <details className="bankRawSummary"><summary>查看银行原始附言</summary><p>{item.summary}</p></details>}
                <dl>
                  <div><dt>余额</dt><dd>{item.balance === null ? "—" : formatMoney(item.balance)}</dd></div>
                  <div><dt>分类</dt><dd>{(!item.category || item.category === "待确认") ? "未分类" : item.category}</dd></div>
                  <div><dt>项目</dt><dd>{transactionProjectLabel(item)}</dd></div>
                </dl>
                {canEditBank && (
                  <button
                    type="button"
                    className="transactionRowEditButton"
                    onClick={() => setEditingTransactionId((current) => current === item.id ? "" : item.id)}
                  >
                    {editingTransactionId === item.id
                      ? "收起"
                      : selected.status === "confirmed" ? "分类 / 用途修正" : "核对 / 用途修正"}
                  </button>
                )}
                {editingTransactionId === item.id && canEditBank && (
                  <div className="transactionEditWorkflow mobileTransactionEditor">
                    <form
                      className="transactionEditExpanded"
                      onSubmit={async (event) => {
                        await onUpdateTransaction(event, item.id);
                        setEditingTransactionId("");
                      }}
                    >
                      <input type="hidden" name="annotation_only" value={selected.status === "confirmed" ? "true" : "false"} />
                      {selected.status !== "confirmed" && <label><span>交易日期与时间</span><input name="transacted_at" type="datetime-local" step="1" defaultValue={toShanghaiDateTimeLocal(item.transacted_at)} required /></label>}
                      {selected.status !== "confirmed" && <label><span>收 / 付款人</span><input name="counterparty" defaultValue={item.counterparty || ""} placeholder="填写银行实际收/付款人" /></label>}
                      {selected.status === "confirmed" && <p className="transactionAnnotationNotice">该流水已经确认；银行原始数据不会被改动。实际用途修正须经创始人复核。</p>}
                      <label><span>财务分类</span><input name="category" defaultValue={item.category || "未分类"} required /></label>
                      <label className={item.project_reference_valid === false ? "invalidFinanceField" : ""}>
                        <span>公司编码 / 项目段</span>
                        {entity.is_headquarters ? (
                          <select name="project_reference" defaultValue={item.project_reference || ""} required>
                            <option value="">请选择公司编码</option>
                            {item.project_reference && !COST_CENTER_OPTIONS.some(([code]) => code === item.project_reference?.toUpperCase()) && <option value={item.project_reference}>{item.project_reference}（需修正）</option>}
                            {COST_CENTER_OPTIONS.map(([code, label]) => <option key={code} value={code}>{code} · {label}</option>)}
                          </select>
                        ) : <input name="project_reference" defaultValue={item.project_reference || ""} placeholder="项目代码" />}
                        {item.project_reference_valid === false && <small>2026 年起京奥流水必须选择有效公司编码后才能确认。</small>}
                      </label>
                      <label><span>关联 JAOS 项目（可选）</span><select name="pm_project_id" defaultValue={item.pm_project_id || ""}><option value="">暂不关联</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.project_no} · {project.name}</option>)}</select></label>
                      {item.summary && <details className="bankRawSummary editorRawSummary"><summary>查看银行原始附言（不可修改）</summary><p>{item.summary}</p></details>}
                      <div className="transactionEditActions">
                        <button type="button" className="secondaryButton" onClick={() => setEditingTransactionId("")}>取消</button>
                        <button type="submit" disabled={busy === `transaction-${item.id}`}>{busy === `transaction-${item.id}` ? "保存中…" : "保存分类与项目"}</button>
                      </div>
                    </form>
                    {renderPurposeCorrectionWorkflow(item)}
                  </div>
                )}
              </article>
            ))}
            {!transactions.length && <p className="mutedText">该批次没有可显示的流水。</p>}
          </div>
        </section>
      )}

    </section>
  );
}

function ProjectManagementWorkspace({
  user,
  registry,
  selected,
  collaboratorCandidates,
  busy,
  message,
  canCreate,
  canReview,
  canArchive,
  canFinanceConfirm,
  deletePasswordConfigured,
  onCreate,
  onUpdate,
  onCollaborators,
  onContractStatus,
  onProcessFinance,
  onRequestDeletion,
  onDeletionDecision,
  onConfigureDeletePassword,
  onFounderDelete,
  onArchive,
  onSelect,
  onCashflow,
  onCashflowActual,
  onSubmitInitiation,
  onProgress,
  onSubmitClosing,
  onReview,
}: {
  user: User;
  registry: ManagedProjectRegistry;
  selected: ManagedProject | null;
  collaboratorCandidates: ProjectCollaboratorAccount[];
  busy: string;
  message: string;
  canCreate: boolean;
  canReview: boolean;
  canArchive: boolean;
  canFinanceConfirm: boolean;
  deletePasswordConfigured: boolean | null;
  onCreate: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onUpdate: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onCollaborators: (usernames: string[]) => Promise<void>;
  onContractStatus: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onProcessFinance: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onRequestDeletion: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onDeletionDecision: (event: FormEvent<HTMLFormElement>, requestId: string) => Promise<void>;
  onConfigureDeletePassword: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onFounderDelete: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onArchive: (action: "archive" | "restore") => Promise<void>;
  onSelect: (projectId: string) => Promise<void>;
  onCashflow: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onCashflowActual: (event: FormEvent<HTMLFormElement>, cashflowId: string) => Promise<void>;
  onSubmitInitiation: () => Promise<void>;
  onProgress: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onSubmitClosing: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onReview: (event: FormEvent<HTMLFormElement>, stage: "initiation" | "closing") => Promise<void>;
}) {
  const projectDetailRef = useRef<HTMLElement | null>(null);
  const isOwner = Boolean(selected && selected.manager_user_id === user.id && user.organization_role === "business");
  const isCollaborator = Boolean(selected?.collaborators?.some((item) => item.user_id === user.id));
  const canEditContent = isOwner || isCollaborator;
  const reviewStage = selected?.status === "initiation_review" ? "initiation" : selected?.status === "closing_review" ? "closing" : null;
  const reviewRows = reviewStage === "initiation" ? selected?.initiation_reviews : selected?.closing_reviews;
  const slot = ["found", "founder"].includes(user.username.toLowerCase()) ? "founder" : "";
  const alreadyReviewed = Boolean(reviewRows?.some((item) => item.slot === slot && item.decision !== "pending"));
  const selectedExecutionTeam = selected ? executionTeamMembers(selected) : [];
  const selectedContractAlert = selected ? managedProjectContractAlert(selected) : false;
  const selectedContractStatus = selected ? managedProjectContractStatus(selected) : "unsigned";
  const portfolioSections = [
    { key: "ongoing", title: "正在进行", hint: "执行、结案准备中的项目", tone: "active" },
    { key: "closed_unpaid", title: "已结案 · 待回款", hint: "继续跟踪回款，暂不能归档", tone: "warning" },
    { key: "pipeline", title: "立项准备", hint: "草稿、复核或退回修改", tone: "pipeline" },
    { key: "ready_archive", title: "回款完成 · 可归档", hint: "已结案且无待回款", tone: "ready" },
    { key: "archived", title: "归档项目", hint: "保留完整记录，可随时恢复", tone: "archived" },
  ].map((section) => ({
    ...section,
    items: registry.items.filter((item) => item.portfolio_group === section.key),
  })).filter((section) => section.items.length > 0);

  async function handleMobileProjectSelect(projectId: string) {
    await onSelect(projectId);
    if (typeof window === "undefined" || !window.matchMedia("(max-width: 760px)").matches) return;
    window.requestAnimationFrame(() => {
      projectDetailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function addCollaborator(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const username = String(data.get("collaborator_username") || "").trim();
    if (!username) return;
    const current = (selected.collaborators || []).map((item) => item.username);
    if (current.some((item) => item.toLowerCase() === username.toLowerCase())) return;
    void onCollaborators([...current, username]).then(() => form.reset());
  }

  function removeCollaborator(username: string) {
    if (!selected || !window.confirm(`确认取消账号 ${username} 对本项目的协作编辑权限？`)) return;
    void onCollaborators(
      (selected.collaborators || [])
        .filter((item) => item.username !== username)
        .map((item) => item.username),
    );
  }

  return (
    <section className="projectManagementWorkspace">
      <section className="pmPortfolioHeader">
        <div><p>JINGAO PROJECT PORTFOLIO</p><h2>项目全流程管理</h2><span>从业务立项、资金计划、过程进度到负责人结案复核。</span></div>
        <div className="pmPortfolioStats">
          <article><strong>{registry.portfolio_counts.ongoing || 0}</strong><span>正在进行</span></article>
          <article><strong>{registry.portfolio_counts.closed_unpaid || 0}</strong><span>结案待回款</span></article>
          <article><strong>{registry.portfolio_counts.ready_archive || 0}</strong><span>可归档</span></article>
          <article><strong>{registry.portfolio_counts.archived || 0}</strong><span>已归档</span></article>
        </div>
      </section>

      {message && <div className="noticeBar successNotice"><strong>流程已更新</strong><span>{message}</span></div>}

      {canCreate && (
        <details className="panel pmCreatePanel" open={!registry.items.length}>
          <summary><span><b>＋ 新建项目立项</b><small>项目代码统一使用公司成本中心格式</small></span></summary>
          <form className="businessForm" onSubmit={onCreate}>
            <label className="pmProjectNoField">
              <span>项目代码（成本中心）</span>
              <input name="project_no" required maxLength={7} pattern={COST_CENTER_CODE_PATTERN} list="cost-center-options-create" autoComplete="off" placeholder="例如：CC26B01" />
              <datalist id="cost-center-options-create">{COST_CENTER_OPTIONS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</datalist>
              <small>统一格式为 CC＋两位年份＋A/B/C＋两位序号；银行流水出现同一代码后会自动归集到本项目。</small>
            </label>
            <div className="formGrid threeColumns">
              <label>项目名称<input name="name" required /></label>
              <label>签约公司主体<input name="company_name" required /></label>
              <label>甲方公司<input name="client" required /></label>
              <label>甲方对接人<input name="client_contact" required placeholder="填写主要对接人姓名" /></label>
              <label>业务分类<input name="business_category" required placeholder="电竞培训 / 赛事 / 场馆…" /></label>
              <label>计划开始<input name="planned_start" type="date" required /></label>
              <label>计划结束<input name="planned_end" type="date" required /></label>
              <label>合同金额<input name="contract_amount" type="number" min="0" step="0.01" defaultValue="0" /></label>
              <label>预算收入<input name="budget_revenue" type="number" min="0" step="0.01" defaultValue="0" /></label>
              <label>预算成本（不含税）<input name="budget_cost" type="number" min="0" step="0.01" defaultValue="0" /></label>
              <label>预计税费<input name="budget_tax" type="number" min="0" step="0.01" defaultValue="0" /></label>
              <label>合同状态<select name="contract_status" defaultValue="unsigned"><option value="unsigned">未签署</option><option value="signed_received">已签署收件</option></select></label>
              <label className="spanTwo">执行团队名单<input name="members" required placeholder="填写除项目经理外参与执行的人员，顿号/逗号分隔" /></label>
              <label>合同资料 ID（选填）<input name="contract_document_id" /></label>
            </div>
            <label>项目目标<textarea name="objective" minLength={4} rows={4} required /></label>
            <label className="fileInputCard">上传立项提案或预算附件（选填）<input name="proposal_file" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.png,.jpg,.jpeg,.zip" /></label>
            <button className="primaryButton" disabled={busy === "create"}>{busy === "create" ? "正在建立…" : "建立项目草稿"}</button>
          </form>
        </details>
      )}

      <section className="pmMainGrid">
        <section className="panel pmProjectListPanel">
          <PanelTitle eyebrow="PROJECT PORTFOLIO" title="项目组合" />
          <div className="pmProjectList">
            {portfolioSections.map((section) => (
              <section className={`pmPortfolioSection ${section.tone}`} key={section.key}>
                <header>
                  <div><strong>{section.title}</strong><small>{section.hint}</small></div>
                  <b>{section.items.length}</b>
                </header>
                <div className="pmPortfolioSectionItems">
                  {section.items.map((item) => (
                    <button type="button" className={`${selected?.id === item.id ? "active" : ""}${managedProjectContractAlert(item) ? " contractAlert" : ""}`} key={item.id} onClick={() => void handleMobileProjectSelect(item.id)}>
                      <span className="pmProjectNo">{item.project_no}</span>
                      <strong>{item.name}</strong>
                      <small>{item.client} · 项目经理 {item.manager}</small>
                      <span className={`pmTeamSummary${executionTeamMembers(item).length ? "" : " empty"}`}>
                        执行：{executionTeamSummary(item)}
                      </span>
                      <span className={`pmContractBadge ${managedProjectContractAlert(item) ? "alert" : managedProjectContractStatus(item)}`}>
                        {managedProjectContractAlert(item) ? "异常 · 合同未签署" : `合同 · ${managedProjectContractLabel(item)}`}
                      </span>
                      <div>
                        <span>{managedProjectStatusNames[item.status] || item.status}</span>
                        {item.portfolio_group === "closed_unpaid"
                          ? <b className="negative">待回 {formatMoney(item.outstanding_receivable)}</b>
                          : <b>{item.progress_percent}%</b>}
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            ))}
            {!registry.items.length && <div className="emptyState compact"><b>▦</b><h3>还没有项目</h3><p>由业务账号建立第一条立项。</p></div>}
          </div>
        </section>

        <section className="panel pmProjectDetailPanel" ref={projectDetailRef}>
          {!selected ? (
            <div className="emptyState"><b>▦</b><h3>选择一个项目查看全貌</h3><p>项目资料、资金计划、进度与复核状态会集中显示。</p></div>
          ) : (
            <>
              <header className="pmDetailHeader">
                <div className="pmDetailIdentity">
                  <div className="pmDetailTopline">
                    <p>{selected.project_no}</p>
                    <b className={`pmStatus ${selected.status}`}>{managedProjectStatusNames[selected.status] || selected.status}</b>
                  </div>
                  <div className="pmDetailHeadline">
                    <h2>{selected.name}</h2>
                    <section className="pmClientSpotlight" aria-label="甲方信息">
                      <span>甲方公司</span>
                      <div>
                        <strong>{selected.client || "待补充甲方公司"}</strong>
                        <small>对接人 · {selected.client_contact || "待补充"}</small>
                      </div>
                    </section>
                  </div>
                  <span>{selected.company_name} · 项目经理 {selected.manager}</span>
                  <div className={`pmExecutionTeam${selectedExecutionTeam.length ? "" : " empty"}`}>
                    <strong>执行团队</strong>
                    <div>
                      {selectedExecutionTeam.length
                        ? selectedExecutionTeam.map((member, index) => <span key={`${member}-${index}`}>{member}</span>)
                        : <span>待补充执行团队名单</span>}
                    </div>
                  </div>
                  <div className={`pmCollaboratorAccess${selected.collaborators?.length ? "" : " empty"}`}>
                    <strong>协作编辑账号</strong>
                    <div className="pmCollaboratorChips">
                      {selected.collaborators?.length
                        ? selected.collaborators.map((account) => (
                            <span key={account.user_id}>
                              <b>{account.display_name}</b>
                              <small>@{account.username}</small>
                              {isOwner && (
                                <button type="button" aria-label={`移除 ${account.display_name} 的协作权限`} onClick={() => removeCollaborator(account.username)}>×</button>
                              )}
                            </span>
                          ))
                        : <span className="pmNoCollaborator">尚未分配协作编辑账号</span>}
                    </div>
                    {isOwner && (
                      <form className="pmCollaboratorForm" onSubmit={addCollaborator}>
                        <input name="collaborator_username" list={`project-collaborators-${selected.id}`} placeholder="输入同事登录账号" required autoComplete="off" />
                        <datalist id={`project-collaborators-${selected.id}`}>
                          {collaboratorCandidates
                            .filter((account) => account.user_id !== selected.manager_user_id && !selected.collaborators?.some((item) => item.user_id === account.user_id))
                            .map((account) => <option key={account.user_id} value={account.username}>{account.display_name}</option>)}
                        </datalist>
                        <button type="submit" disabled={busy === "collaborators"}>{busy === "collaborators" ? "保存中…" : "添加协作成员"}</button>
                      </form>
                    )}
                  </div>
                </div>
              </header>
              <section className={`pmContractStatusPanel ${selectedContractAlert ? "alert" : selectedContractStatus}`} role={selectedContractAlert ? "alert" : undefined}>
                <div className="pmContractStatusCopy">
                  <span>CONTRACT STATUS</span>
                  <h3>{selectedContractAlert ? "项目已启动，合同仍未签署" : selectedContractStatus === "signed_received" ? "合同已签署收件" : "合同尚未签署"}</h3>
                  <p>{selectedContractAlert
                    ? selected.contract_alert_message || "该项目已进入执行或结案流程，请尽快完成合同签署并确认收件。"
                    : selectedContractStatus === "signed_received"
                      ? "合同状态正常；已记录签署并收到合同原件。"
                      : "项目尚未启动，建议在进入执行前完成合同签署收件。"}</p>
                </div>
                {canEditContent && (
                  <form className="pmContractStatusForm" onSubmit={onContractStatus}>
                    <label htmlFor={`contract-status-${selected.id}`}>更新合同状态</label>
                    <div>
                      <select id={`contract-status-${selected.id}`} name="contract_status" defaultValue={selectedContractStatus} key={`${selected.id}-${selectedContractStatus}`}>
                        <option value="unsigned">未签署</option>
                        <option value="signed_received">已签署收件</option>
                      </select>
                      <button type="submit" disabled={busy === "contract-status"}>{busy === "contract-status" ? "更新中…" : "保存状态"}</button>
                    </div>
                  </form>
                )}
              </section>
              <div className="pmProgressTrack"><span style={{ width: `${selected.progress_percent}%` }} /><b>{selected.progress_percent}%</b></div>
              <section className="pmFinancialSummary">
                <article><span>合同金额</span><strong>{formatMoney(selected.contract_amount)}</strong></article>
                <article><span>预算收入</span><strong>{formatMoney(selected.budget_revenue)}</strong></article>
                <article><span>预算成本（不含税）</span><strong>{formatMoney(selected.budget_cost)}</strong></article>
                <article><span>预计税费</span><strong>{formatMoney(selected.budget_tax ?? 0)}</strong></article>
                <article><span>预计毛利</span><strong className={Number(selected.expected_margin) >= 0 ? "positive" : "negative"}>{formatMoney(selected.expected_margin)}</strong></article>
                <article><span>最大垫资缺口</span><strong className="negative">{formatMoney(selected.maximum_funding_gap ?? 0)}</strong></article>
              </section>
              <section className="pmProcessFinanceSection">
                <header>
                  <div><span>FINANCE LINKED CASH</span><strong>项目过程资金</strong></div>
                  <small>已自动归集 {selected.bank_transaction_count || 0} 笔已确认银行流水</small>
                </header>
                <div className="pmProcessFinanceSummary">
                  <article className="received"><span>已收入</span><strong>{formatMoney(selected.bank_received ?? selected.process_received ?? 0)}</strong><small>已确认流水自动同步</small></article>
                  <article className="spent"><span>已支出</span><strong>{formatMoney(selected.bank_spent ?? selected.process_spent ?? 0)}</strong><small>已确认流水自动同步</small></article>
                  <article className="advanced"><span>已垫资</span><strong>{formatMoney(selected.process_advanced ?? 0)}</strong><small>PM累计填报</small></article>
                </div>
                {canEditContent && ["active", "closing_rejected"].includes(selected.status) && (
                  <details className="pmProcessFinanceEditor">
                    <summary>维护 PM 备查口径与垫资</summary>
                    <form key={`${selected.id}-${selected.process_finance_updated_at || "new"}`} onSubmit={onProcessFinance}>
                      <label>PM备查累计收入<input name="process_received" type="number" min="0" step="0.01" defaultValue={Number(selected.process_received || 0)} required /></label>
                      <label>PM备查累计支出<input name="process_spent" type="number" min="0" step="0.01" defaultValue={Number(selected.process_spent || 0)} required /></label>
                      <label>累计已垫资<input name="process_advanced" type="number" min="0" step="0.01" defaultValue={Number(selected.process_advanced || 0)} required /></label>
                      <button type="submit" disabled={busy === "process-finance"}>{busy === "process-finance" ? "保存中…" : "保存过程资金"}</button>
                    </form>
                    <p>“已收入/已支出”卡片以财务确认的银行流水为准；这里保留项目团队备查口径，并维护尚未经过公司账户的垫资。</p>
                  </details>
                )}
              </section>
              <section className="pmBrief"><div><span>周期</span><b>{selected.planned_start} 至 {selected.planned_end}</b></div><div><span>当前阶段</span><b>{selected.current_stage}</b></div><p>{selected.objective}</p></section>

              {["closed", "archived"].includes(selected.status) && (
                <section className={`pmPaymentStatus ${selected.payment_complete ? "complete" : "pending"}`}>
                  <div>
                    <span>{selected.status === "archived" ? "ARCHIVED PROJECT" : "PAYMENT CLEARANCE"}</span>
                    <h3>{selected.status === "archived" ? "项目已归档" : selected.payment_complete ? "回款已完成，可以归档" : "项目已结案，仍需跟踪回款"}</h3>
                    <p>计划应收 {formatMoney(selected.planned_receivable)} · 已回款 {formatMoney(selected.received_amount)} · 待回款 {formatMoney(selected.outstanding_receivable)}</p>
                  </div>
                  {canArchive && selected.status === "closed" && selected.payment_complete && (
                    <button type="button" onClick={() => void onArchive("archive")} disabled={busy === "project-archive"}>归档项目</button>
                  )}
                  {canArchive && selected.status === "archived" && (
                    <button type="button" onClick={() => void onArchive("restore")} disabled={busy === "project-archive"}>恢复项目</button>
                  )}
                  {selected.status === "closed" && !selected.payment_complete && <b>待回款项目不能归档</b>}
                </section>
              )}

              {canEditContent && ["draft", "initiation_rejected", "active", "closing_rejected"].includes(selected.status) && (
                <details className="pmProjectControlPanel">
                  <summary>修改项目基础信息、执行团队与预算</summary>
                  <form className="businessForm" onSubmit={onUpdate}>
                    <label className="pmProjectNoField">
                      <span>项目代码（成本中心）</span>
                      <input name="project_no" required maxLength={40} pattern={isOwner ? COST_CENTER_CODE_PATTERN : undefined} readOnly={!isOwner} list={isOwner ? `cost-center-options-${selected.id}` : undefined} defaultValue={selected.project_no} autoComplete="off" />
                      {isOwner && <datalist id={`cost-center-options-${selected.id}`}>{COST_CENTER_OPTIONS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</datalist>}
                      <small>{isOwner ? (isCostCenterCode(selected.project_no) ? "项目经理可修改；改码后相同代码的未关联流水会自动补充关联。" : "当前为历史代码，保存其他修改前请改为最新 CC 成本中心格式。") : "只有项目经理可以修改项目代码。"}</small>
                    </label>
                    <div className="formGrid threeColumns">
                      <label>项目名称<input name="name" defaultValue={selected.name} required /></label>
                      <label>签约公司主体<input name="company_name" defaultValue={selected.company_name} required /></label>
                      <label>甲方公司<input name="client" defaultValue={selected.client} required /></label>
                      <label>甲方对接人<input name="client_contact" defaultValue={selected.client_contact || ""} required placeholder="填写主要对接人姓名" /></label>
                      <label>业务分类<input name="business_category" defaultValue={selected.business_category} required /></label>
                      <label>计划开始<input name="planned_start" type="date" defaultValue={selected.planned_start} required /></label>
                      <label>计划结束<input name="planned_end" type="date" defaultValue={selected.planned_end} required /></label>
                      <label>合同金额<input name="contract_amount" type="number" min="0" step="0.01" defaultValue={Number(selected.contract_amount || 0)} /></label>
                      <label>预算收入<input name="budget_revenue" type="number" min="0" step="0.01" defaultValue={Number(selected.budget_revenue || 0)} /></label>
                      <label>预算成本（不含税）<input name="budget_cost" type="number" min="0" step="0.01" defaultValue={Number(selected.budget_cost || 0)} /></label>
                      <label>预计税费<input name="budget_tax" type="number" min="0" step="0.01" defaultValue={Number(selected.budget_tax || 0)} /></label>
                      <label>合同状态<select name="contract_status" defaultValue={selectedContractStatus}><option value="unsigned">未签署</option><option value="signed_received">已签署收件</option></select></label>
                      <label className="spanTwo">执行团队名单<input name="members" required defaultValue={selectedExecutionTeam.join("、")} placeholder="填写除项目经理外参与执行的人员，顿号/逗号分隔" /></label>
                      <label>合同资料 ID（选填）<input name="contract_document_id" defaultValue={selected.contract_document_id || ""} /></label>
                    </div>
                    <label>项目目标<textarea name="objective" minLength={4} rows={4} defaultValue={selected.objective} required /></label>
                    <button className="primaryButton" disabled={busy === "project-update"}>{busy === "project-update" ? "保存中…" : "保存项目修改"}</button>
                  </form>
                </details>
              )}

              <section className="pmProjectAdminFooter" aria-label="项目管理记录">
                <header><span>PROJECT ADMINISTRATION</span><strong>管理记录</strong><small>复核与删除操作集中收纳于此</small></header>

                <details className="pmManagementItem pmReviewSection" defaultOpen={Boolean(canReview && reviewStage && !alreadyReviewed)} key={`${selected.id}-review-${reviewStage || "none"}-${alreadyReviewed ? "done" : "open"}`}>
                  <summary>
                    <div><strong>负责人复核</strong><small>测试阶段由叶靖波复核</small></div>
                    <span className={alreadyReviewed ? "complete" : reviewStage ? "pending" : "neutral"}>{alreadyReviewed ? "已完成" : reviewStage ? "待复核" : "暂无待办"}</span>
                  </summary>
                  <div className="pmManagementBody">
                    <div className="reviewSlotGrid">
                      {(selected.status.includes("closing") || selected.status === "closed" ? selected.closing_reviews : selected.initiation_reviews)?.map((item) => (
                        <article className={item.decision} key={item.slot}><span>{item.label}</span><strong>{item.decision === "approved" ? "已通过" : item.decision === "rejected" ? "已退回" : "待复核"}</strong><small>{item.reviewer || "等待处理"}{item.note ? ` · ${item.note}` : ""}</small></article>
                      ))}
                    </div>
                    {canReview && reviewStage && !alreadyReviewed && (
                      <form className="inlineReviewForm" onSubmit={(event) => void onReview(event, reviewStage)}>
                        <select name="decision" defaultValue="approved"><option value="approved">通过</option><option value="rejected">退回</option></select>
                        <input name="note" placeholder="复核意见（退回时建议填写）" />
                        <button className="primaryButton" disabled={busy === `review-${reviewStage}`}>提交我的复核</button>
                      </form>
                    )}
                  </div>
                </details>

                <details className="pmManagementItem pmDeletionPanel" defaultOpen={selected.deletion_request?.status === "pending"} key={`${selected.id}-deletion-${selected.deletion_request?.status || "none"}`}>
                  <summary>
                    <div><strong>项目删除</strong><small>项目经理可申请；创始人删除必须验证独立密码</small></div>
                    <span className={selected.deletion_request?.status === "pending" ? "danger" : selected.deletion_request?.status === "rejected" ? "rejected" : "neutral"}>{selected.deletion_request?.status === "pending" ? "待复核" : selected.deletion_request?.status === "rejected" ? "已驳回" : "无申请"}</span>
                  </summary>
                  <div className="pmManagementBody">
                    {selected.deletion_request?.status === "pending" ? (
                      <div className="pmDeletionPending">
                        <strong>等待叶靖波复核删除</strong>
                        <p>{selected.deletion_request.reason}</p>
                        <small>申请人：{selected.deletion_request.requester}</small>
                        {canReview && (
                          <form className="inlineReviewForm deletionReviewForm" onSubmit={(event) => void onDeletionDecision(event, selected.deletion_request!.id)}>
                            <select name="decision" defaultValue="rejected"><option value="rejected">驳回删除</option><option value="approved">批准删除</option></select>
                            <input name="note" placeholder="删除复核意见（选填）" />
                            <input name="deletion_password" type="password" autoComplete="off" placeholder="批准删除时输入删除密码" />
                            <button className="primaryButton" disabled={busy === "deletion-decision"}>提交删除复核</button>
                          </form>
                        )}
                      </div>
                    ) : isOwner ? (
                      <form className="pmDeletionRequestForm" onSubmit={onRequestDeletion}>
                        {selected.deletion_request?.status === "rejected" && <p>上次删除申请已被驳回：{selected.deletion_request.decision_note || "未填写原因"}</p>}
                        <input name="reason" minLength={2} maxLength={1000} required placeholder="说明为什么需要删除这个项目" />
                        <button type="submit" disabled={busy === "deletion-request"}>申请删除项目</button>
                      </form>
                    ) : (
                      <p>只有项目经理可以发起删除申请，批准权归叶靖波。</p>
                    )}
                    {canReview && (
                      <section className="pmFounderDeleteControl">
                        <header>
                          <div>
                            <span>FOUNDER SECURITY</span>
                            <strong>创始人直接删除</strong>
                            <small>仅执行软删除；项目代码、附件、财务关联和审计记录仍保留。</small>
                          </div>
                          <b className={deletePasswordConfigured ? "configured" : "unconfigured"}>
                            {deletePasswordConfigured === null ? "读取中" : deletePasswordConfigured ? "删除密码已设置" : "尚未设置删除密码"}
                          </b>
                        </header>

                        {deletePasswordConfigured && (
                          <form className="pmFounderDeleteForm" onSubmit={onFounderDelete}>
                            <label>删除原因<input name="reason" minLength={2} maxLength={1000} required placeholder="说明删除原因，内容将写入审计日志" /></label>
                            <label>项目删除密码<input name="deletion_password" type="password" required autoComplete="off" placeholder="输入独立删除密码" /></label>
                            <button type="submit" disabled={busy === "founder-delete"}>{busy === "founder-delete" ? "正在删除…" : "验证密码并删除项目"}</button>
                          </form>
                        )}

                        {deletePasswordConfigured !== null && (
                          <details className="pmDeletePasswordSettings" open={!deletePasswordConfigured}>
                            <summary>{deletePasswordConfigured ? "修改项目删除密码" : "首次设置项目删除密码"}</summary>
                            <form onSubmit={onConfigureDeletePassword}>
                              <label>当前登录密码<input name="current_login_password" type="password" required autoComplete="current-password" /></label>
                              <label>新的删除密码<input name="new_password" type="password" required minLength={8} maxLength={200} autoComplete="new-password" placeholder="至少 8 位，且不能与登录密码相同" /></label>
                              <label>再次输入删除密码<input name="confirm_password" type="password" required minLength={8} maxLength={200} autoComplete="new-password" /></label>
                              <button type="submit" disabled={busy === "delete-password"}>{busy === "delete-password" ? "保存中…" : deletePasswordConfigured ? "确认修改删除密码" : "设置删除密码"}</button>
                            </form>
                            <p>删除密码只以加盐哈希保存在 JAOS 数据库，不保存或显示明文；设置和修改均需验证当前登录密码。</p>
                          </details>
                        )}
                      </section>
                    )}
                  </div>
                </details>
              </section>

              <section className="pmCashflowSection">
                <div className="sectionHeading"><div><span>CASHFLOW PLAN</span><h3>应收应付与资金周期</h3></div></div>
                <div className="tableScroll desktopDataTable pmCashflowTable"><table className="businessTable"><thead><tr><th>方向</th><th>计划日期</th><th>金额</th><th>对方</th><th>累计现金</th><th>实际收付</th></tr></thead><tbody>
                  {(selected.cashflow_plans || []).map((item) => (
                    <tr key={item.id}><td>{item.direction === "receivable" ? "应收" : "应付"}</td><td>{item.due_date}</td><td>{formatMoney(item.amount)}</td><td>{item.counterparty || "—"}</td><td className={Number(item.running_cash) >= 0 ? "positive" : "negative"}>{formatMoney(item.running_cash)}</td><td>{canFinanceConfirm ? <form className="actualForm" onSubmit={(event) => void onCashflowActual(event, item.id)}><input name="actual_amount" type="number" min="0" step="0.01" defaultValue={Number(item.actual_amount || 0)} /><input name="actual_date" type="date" defaultValue={item.actual_date || ""} /><button>确认</button></form> : item.actual_date ? `${item.actual_date} · ${formatMoney(item.actual_amount)}` : "未发生"}</td></tr>
                  ))}
                  {!(selected.cashflow_plans || []).length && <tr><td colSpan={6}>尚未登记收付款计划。</td></tr>}
                </tbody></table></div>
                <div className="mobileDataCards pmCashflowCards" aria-label="手机端项目现金流计划">
                  {(selected.cashflow_plans || []).map((item) => (
                    <article className={`mobileDataCard pmCashflowCard ${item.direction}`} key={item.id}>
                      <header>
                        <div>
                          <span>{item.direction === "receivable" ? "应收计划" : "应付计划"}</span>
                          <strong>{item.counterparty || "未填写对方单位"}</strong>
                        </div>
                        <b className={item.direction === "receivable" ? "positive" : "negative"}>{formatMoney(item.amount)}</b>
                      </header>
                      <dl>
                        <div><dt>计划日期</dt><dd>{item.due_date}</dd></div>
                        <div><dt>累计现金</dt><dd className={Number(item.running_cash) >= 0 ? "positive" : "negative"}>{formatMoney(item.running_cash)}</dd></div>
                        <div><dt>实际收付</dt><dd>{item.actual_date ? `${item.actual_date} · ${formatMoney(item.actual_amount)}` : "未发生"}</dd></div>
                      </dl>
                      {item.note && <p>{item.note}</p>}
                      {canFinanceConfirm && (
                        <form className="actualForm mobileActualForm" onSubmit={(event) => void onCashflowActual(event, item.id)}>
                          <label>实际金额<input name="actual_amount" type="number" min="0" step="0.01" defaultValue={Number(item.actual_amount || 0)} /></label>
                          <label>实际日期<input name="actual_date" type="date" defaultValue={item.actual_date || ""} /></label>
                          <button>确认实际收付</button>
                        </form>
                      )}
                    </article>
                  ))}
                  {!(selected.cashflow_plans || []).length && <p className="mutedText">尚未登记收付款计划。</p>}
                </div>
                {selected.closing_summary && (
                  <section className="mobileProjectSettlement" aria-label="手机端项目决算">
                    <header><span>PROJECT SETTLEMENT</span><h4>项目结案决算</h4></header>
                    <p>{selected.closing_summary}</p>
                    <dl>
                      <div><dt>实际收入</dt><dd className="positive">{formatMoney(selected.actual_revenue ?? 0)}</dd></div>
                      <div><dt>实际成本</dt><dd className="negative">{formatMoney(selected.actual_cost ?? 0)}</dd></div>
                      <div><dt>未收金额</dt><dd>{formatMoney(selected.actual_receivable ?? 0)}</dd></div>
                      <div><dt>未付金额</dt><dd>{formatMoney(selected.actual_payable ?? 0)}</dd></div>
                    </dl>
                  </section>
                )}
                {canEditContent && ["draft", "initiation_rejected", "active", "closing_rejected"].includes(selected.status) && (
                  <form className="compactBusinessForm" onSubmit={onCashflow}>
                    <select name="direction" defaultValue="receivable"><option value="receivable">应收</option><option value="payable">应付</option></select>
                    <input name="due_date" type="date" required />
                    <input name="amount" type="number" min="0.01" step="0.01" placeholder="金额" required />
                    <input name="counterparty" placeholder="对方单位" />
                    <input name="note" placeholder="说明" />
                    <button>新增计划</button>
                  </form>
                )}
              </section>

              {isOwner && ["draft", "initiation_rejected"].includes(selected.status) && <button className="primaryButton pmPrimaryAction" onClick={() => void onSubmitInitiation()} disabled={busy === "submit-initiation"}>提交立项复核</button>}

              {canEditContent && selected.status === "active" && (
                <section className="pmActionGrid">
                  <form className="businessForm" onSubmit={onProgress}>
                    <h3>更新项目进度</h3>
                    <div className="formGrid twoColumns"><label>完成度<input name="progress_percent" type="number" min="0" max="100" defaultValue={selected.progress_percent} required /></label><label>当前阶段<input name="current_stage" defaultValue={selected.current_stage} required /></label></div>
                    <label>本期完成<textarea name="completed" rows={3} required /></label><label>下一步<textarea name="next_step" rows={3} required /></label><label>风险<textarea name="risks" rows={2} /></label><label className="checkboxLine"><input name="needs_coordination" type="checkbox" />需要管理层协调</label>
                    <button className="secondaryButton" disabled={busy === "progress"}>保存进度</button>
                  </form>
                  {isOwner && (
                    <form className="businessForm" onSubmit={onSubmitClosing}>
                      <h3>提交项目结案</h3>
                      <label>结案总结<textarea name="closing_summary" rows={4} required /></label>
                      <div className="formGrid twoColumns"><label>实际收入<input name="actual_revenue" type="number" min="0" step="0.01" required /></label><label>实际成本<input name="actual_cost" type="number" min="0" step="0.01" required /></label><label>未收金额<input name="actual_receivable" type="number" min="0" step="0.01" defaultValue="0" /></label><label>未付金额<input name="actual_payable" type="number" min="0" step="0.01" defaultValue="0" /></label></div>
                      <label className="fileInputCard">结案报告（选填）<input name="closing_file" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.png,.jpg,.jpeg,.zip" /></label>
                      <button className="primaryButton" disabled={busy === "closing"}>提交结案复核</button>
                    </form>
                  )}
                </section>
              )}

              {(selected.progress_updates || []).length > 0 && <section className="pmTimeline"><div className="sectionHeading"><div><span>PROGRESS LOG</span><h3>过程记录</h3></div></div>{selected.progress_updates?.map((item) => <article key={item.id}><i /><div><strong>{item.current_stage} · {item.progress_percent}%</strong><span>{item.completed}</span><small>{new Date(item.created_at).toLocaleString("zh-CN")} · {item.creator}</small></div></article>)}</section>}
            </>
          )}
        </section>
      </section>
    </section>
  );
}

function StatCard({ tone, label, value, note }: { tone: string; label: string; value: number; note: string }) {
  return <article className={`statCard ${tone}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function evolutionClassLabel(candidate: EvolutionCandidate) {
  return {
    material: "重要更新",
    review: "建议复核",
    defer: "暂缓",
    blocked: "审批前阻断",
    conflict: "资料冲突",
  }[candidate.classification];
}

function evolutionGateLabel(value: string) {
  const labels: Record<string, string> = {
    external_disclosure_unapproved: "尚未获得对外披露批准",
    conflicting_current_sources: "同一主题存在相互冲突的当前资料",
  };
  return labels[value] || value;
}

function evolutionRunStatusLabel(value: string) {
  const labels: Record<string, string> = {
    open: "候选审批中",
    plan_ready: "变更计划已生成",
    reviewed: "复核已完成",
    baseline_changed: "基线已更新",
  };
  return labels[value] || value;
}

function evolutionDecisionLabel(reviewStatus: string, disclosureStatus: string) {
  if (reviewStatus === "accepted") {
    return disclosureStatus === "approved_external" ? "已纳入并批准对外披露" : "已纳入变更计划";
  }
  if (reviewStatus === "rejected") return "本次不纳入";
  if (reviewStatus === "deferred") return "低优先级 · 暂缓";
  return disclosureStatus === "needs_founder_approval" ? "等待创始人披露审批" : "等待人工决策";
}

function OperationCard({
  label,
  component,
}: {
  label: string;
  component?: OperationComponent;
}) {
  const state = component?.status || "warning";
  const stateLabel = {
    ok: "正常",
    warning: "需关注",
    critical: "严重",
    configured: "已配置",
    disabled: "本地模式",
  }[state] || state;
  let metric = "";
  if (component?.used_percent != null) {
    metric = `${component.used_percent}%`;
    if (component.free_gb != null) metric += ` · 剩余 ${component.free_gb} GB`;
  } else if (component?.open_issue_count != null && component.open_issue_count > 0) {
    metric = `${component.open_issue_count} 个未解决文件`;
  } else if (component?.unhealthy_count != null && component.unhealthy_count > 0) {
    metric = `${component.unhealthy_count} 份原件需恢复`;
  } else if (component?.age_seconds != null) {
    metric = `${Math.round(component.age_seconds / 3600)} 小时前完成`;
  } else if (component?.embedding_model) {
    const generation = component.llm_enabled
      ? `生成：${component.primary_model} → ${component.fallback_model}`
      : "生成关闭";
    const embedding = component.embedding_enabled
      ? `Embedding：${component.embedding_model}`
      : "Embedding 关闭";
    metric = `${generation} · ${embedding}`;
  }
  return (
    <article className={`operationCard ${state}`}>
      <div><span>{label}</span><b>{stateLabel}</b></div>
      <strong>{component?.message || "正在检查…"}</strong>
      {metric && <small>{metric}</small>}
    </article>
  );
}

function writingInline(value: string) {
  return value
    .split(/(\*\*[^*]+\*\*|\[S\d+\])/g)
    .filter(Boolean)
    .map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
      }
      if (/^\[S\d+\]$/.test(part)) {
        return <span className="draftCitation" key={`${part}-${index}`}>{part}</span>;
      }
      return part;
    });
}

function MarkdownDraft({ content }: { content: string }) {
  return content.split(/\r?\n/).map((rawLine, index) => {
    const line = rawLine.trim();
    const key = `${index}-${line.slice(0, 24)}`;
    if (!line) return <div className="draftSpacer" key={key} />;
    if (line.startsWith("### ")) return <h3 key={key}>{writingInline(line.slice(4))}</h3>;
    if (line.startsWith("## ")) return <h2 key={key}>{writingInline(line.slice(3))}</h2>;
    if (line.startsWith("# ")) return <h1 key={key}>{writingInline(line.slice(2))}</h1>;
    if (/^[-*]\s+/.test(line)) {
      return <p className="draftBullet" key={key}><span>•</span><span>{writingInline(line.replace(/^[-*]\s+/, ""))}</span></p>;
    }
    if (/^\d+[.、]\s*/.test(line)) {
      const matched = line.match(/^(\d+[.、])\s*(.*)$/);
      return <p className="draftNumber" key={key}><b>{matched?.[1]}</b><span>{writingInline(matched?.[2] || line)}</span></p>;
    }
    if (line.startsWith("> ")) return <blockquote key={key}>{writingInline(line.slice(2))}</blockquote>;
    return <p key={key}>{writingInline(line)}</p>;
  });
}

function PanelTitle({ eyebrow, title, action, onAction }: { eyebrow: string; title: string; action?: string; onAction?: () => void }) {
  return (
    <div className="panelHead">
      <div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>
      {action && <button type="button" onClick={onAction}>{action} →</button>}
    </div>
  );
}

function ProjectRows({
  projects,
  categoryNames,
}: {
  projects: Project[];
  categoryNames: Record<string, string>;
}) {
  if (!projects.length) return <div className="emptyRows">尚未入库项目</div>;
  return (
    <div className="projectRows">
      {projects.map((project) => {
        return (
          <article className="projectRow" key={project.id}>
            <div className="docIcon">案</div>
            <div className="projectMain">
              <strong>{project.name}</strong>
              <span>{project.client || "客户待确认"} · {project.year || "年份待确认"}</span>
            </div>
            <span className="domainTag">{categoryNames[project.domain] || project.domain}</span>
            {project.closing_report_reminder && <span className="closingBadge">待结案</span>}
            <span className="docs">{project.document_count} 份资料</span>
            <span className={["current", "approved"].includes(project.knowledge_status) ? "currentBadge" : "candidateBadge"}>
              {project.knowledge_status === "current"
                ? "当前"
                : project.knowledge_status === "approved"
                  ? "已入库"
                  : project.knowledge_status === "candidate"
                    ? "候选"
                    : "历史"}
            </span>
          </article>
        );
      })}
    </div>
  );
}

function QuickAction({ icon, title, note, onClick }: { icon: string; title: string; note: string; onClick: () => void }) {
  return (
    <button type="button" className="quickAction" onClick={onClick}>
      <span>{icon}</span><div><strong>{title}</strong><small>{note}</small></div><b>→</b>
    </button>
  );
}

function CompactAnswer({ response }: { response: SearchResponse }) {
  const mode = response.retrieval_mode === "hybrid"
    ? "关键词+语义"
    : response.retrieval_mode === "semantic"
      ? "语义"
      : "确定性";
  return (
    <div className="compactAnswer">
      <strong>{response.answer}</strong>
      <span>
        {response.scope === "current" ? "当前事实检索" : "历史资料检索"} · {mode} · {
          response.generation_mode === "llm" ? "AI证据回答" : "本地证据结果"
        } · {response.total || response.results.length} 份相关资料
        {response.unavailable_count > 0 ? ` · ${response.unavailable_count} 份原件失联已隔离` : ""}
      </span>
    </div>
  );
}

function FullAnswer({
  response,
  previewBusy,
  onPreview,
  loadingMore,
  onLoadMore,
}: {
  response: SearchResponse;
  previewBusy: string;
  onPreview: (documentId: string, page: number) => void;
  loadingMore?: boolean;
  onLoadMore?: () => void;
}) {
  const mode = response.retrieval_mode === "hybrid"
    ? "关键词 + 语义融合"
    : response.retrieval_mode === "semantic"
      ? "语义检索"
      : "确定性检索";
  return (
    <div className="fullAnswer">
      <div className="answerSummary">
        <span>
          {response.scope === "current" ? "当前事实" : "历史资料"} · {mode} · {
            response.generation_mode === "llm" ? "AI证据回答" : "本地证据结果"
          }
        </span>
        <h3>{response.answer}</h3>
      </div>
      {response.retrieval_degraded && (
        <div className="sourceWarning">
          语义服务暂不可用，本次已自动降级为确定性检索，引用与权限规则不变。
        </div>
      )}
      {response.generation_degraded && (
        <div className="sourceWarning">
          AI 生成服务暂不可用，本次保留本地检索结果与原页引用，未丢失证据。
        </div>
      )}
      {response.generation_mode === "local_only" && (
        <div className="sourceWarning">
          本次命中资料受出网规则保护，只在本地返回检索证据，未发送到生成模型。
        </div>
      )}
      {response.unavailable_count > 0 && (
        <div className="sourceWarning">
          另有 {response.unavailable_count} 份相关资料因原件失联，已自动隔离且未用于本次答案。
        </div>
      )}
      <div className="citationList">
        {response.results.map((result, index) => (
          <article key={`${result.document_id}-${result.page}`}>
            <div className="citationIndex">{index + 1}</div>
            <div>
              <div className="citationMeta">
                <strong>{result.title}</strong>
                <span>{confidentialityLabel(result.confidentiality)}</span>
                <span>{result.knowledge_status === "current" ? "当前" : result.knowledge_status === "approved" ? "已入库" : "历史"}</span>
              </div>
              <p>{result.excerpt}</p>
              <div className="citationFooter">
                <small>
                  {result.project} · {result.citation_basis === "slide" ? `第 ${result.page} 页幻灯片` : `第 ${result.page} 页`} · 版本 {result.version}
                  {(result.matched_pages || []).filter((page) => page !== result.page).length > 0
                    ? ` · 另命中第 ${(result.matched_pages || []).filter((page) => page !== result.page).join("、")} 页`
                    : ""}
                </small>
                <button
                  type="button"
                  className="previewLink"
                  disabled={previewBusy === `${result.document_id}-${result.page}`}
                  onClick={() => onPreview(result.document_id, result.page)}
                >
                  {previewBusy === `${result.document_id}-${result.page}` ? "打开中…" : "查看引用原页"}
                </button>
              </div>
            </div>
          </article>
        ))}
        {!response.results.length && <div className="noEvidence">没有可引用证据，因此未生成结论。</div>}
      </div>
      {onLoadMore && response.total > response.results.length && (
        <div className="searchLoadMore">
          <span>共 {response.total} 份相关资料，已显示 {response.results.length} 份</span>
          <button type="button" className="secondaryButton" disabled={loadingMore} onClick={onLoadMore}>
            {loadingMore ? "继续加载中…" : "继续显示更多"}
          </button>
        </div>
      )}
    </div>
  );
}
