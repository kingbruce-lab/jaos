import React, { type ComponentProps, type FormEvent, useState } from "react";
import { createRoot } from "react-dom/client";
import { FinanceWorkspace } from "../app/page";
import "../app/globals.css";
import "../app/project-management.css";
import "../app/finance-workspace.css";

// Synthetic local data only. Every network read is handled below; no production
// account, bank record, upload, token or external request is used by this fixture.
type Props = ComponentProps<typeof FinanceWorkspace>;
type Dashboard = NonNullable<Props["dashboard"]>;
type Annual = NonNullable<Props["annualDashboard"]>;
type Batch = Props["batches"][number];
type Transaction = Props["transactions"][number];
type Correction = Props["purposeCorrections"]["items"][number];
type Obligation = NonNullable<Dashboard["receivables_payables"]>["receivable"]["items"][number];
const companyName = "京奥电竞（北京）科技有限公司";
const clientName = "天竞华娱（苏州）文化传播有限公司及联合电竞赛事运营事业部";
const rawSummary = "银行原始附言：2026训练服务合同首期回款，不可覆盖";
const entities: Props["entities"] = [
  { id: "entity-jingao", key: "jingao", name: companyName, display_name: "京奥电竞", business_name: "集团总部与电竞赛事运营", account_label: "公司银行账户", default_bank_name: "北京银行成寿寺支行", is_headquarters: true, show_cash: true },
  { id: "entity-ace", key: "ace-leopard", name: "王牌猎豹电竞文化发展有限公司", display_name: "王牌猎豹", business_name: "JAG三角洲国际赛事与青训业务", account_label: "独立公司银行账户", default_bank_name: "招商银行", is_headquarters: false, show_cash: false },
  { id: "entity-power", key: "power-leopard", name: "劲腾豹跃电竞科技有限公司", display_name: "劲腾豹跃", business_name: "JAG王者荣耀俱乐部与商业合作", account_label: "独立公司银行账户", default_bank_name: "工商银行", is_headquarters: false, show_cash: false },
];
const ranks = [{ name: clientName, amount: "1200000.25", transaction_count: 12 }, { name: "跨区域电竞人才培养及赛事执行联合服务供应商有限公司", amount: "250000.75", transaction_count: 6 }];
const alert: Dashboard["anomalies"][number] = { id: "alert-1", batch_id: "batch-confirmed", transaction_date: "2026-10-20", counterparty: clientName, summary: rawSummary, income: "1200000.25", expense: "0", amount: "1200000.25", status: "confirmed", severity: "medium", reasons: ["首次出现往来单位，需要核对业务关系"], alert_type: "new_counterparty" };
const obligation: Obligation = { id: "obligation-1", source: "finance", entity_id: entities[0].id, project_id: null, project_no: null, project_name: null, direction: "receivable", due_date: "2026-10-01", amount: "250000.25", actual_amount: "50000", outstanding_amount: "200000.25", counterparty: clientName, note: "非项目活动服务尾款", overdue: true };
const initialBatches: Batch[] = [
  { id: "batch-confirmed", entity_id: entities[0].id, company: companyName, bank_name: "北京银行成寿寺支行", account: "基本户 · ****5678", filename: "2026年10月公司银行流水_已核对.xlsx", period_start: "2026-10-01", period_end: "2026-10-24", status: "confirmed", row_count: 2, duplicate_count: 0, error_count: 0, uploader: "测试财务", confirmer: "测试财务", confirmed_at: "2026-10-24T08:00:00Z", created_at: "2026-10-24T07:00:00Z" },
  { id: "batch-pending", entity_id: entities[0].id, company: companyName, bank_name: "北京银行成寿寺支行", account: "一般户 · ****1234", filename: "2026年10月补充流水_待确认.csv", period_start: "2026-10-20", period_end: "2026-10-24", status: "pending", row_count: 1, duplicate_count: 1, error_count: 0, uploader: "测试财务", confirmer: "", confirmed_at: null, created_at: "2026-10-24T09:00:00Z" },
  { id: "batch-other", entity_id: entities[1].id, company: entities[1].name, bank_name: "招商银行", account: "基本户 · ****8888", filename: "王牌猎豹2026年10月流水.xlsx", period_start: "2026-10-01", period_end: "2026-10-24", status: "confirmed", row_count: 0, duplicate_count: 0, error_count: 0, uploader: "测试财务", confirmer: "测试财务", confirmed_at: "2026-10-24T08:00:00Z", created_at: "2026-10-24T07:00:00Z" },
];
const initialCorrection: Correction = { id: "correction-1", transaction_id: "transaction-2", entity_id: entities[0].id, previous_purpose: "场地服务", proposed_purpose: "电竞青训营场地及设备租赁服务", status: "pending", requested_by: "测试财务", requested_at: "2026-10-24T10:00:00Z", reviewed_by: "", reviewed_at: null, review_comment: null, transaction: { transacted_at: "2026-10-20T04:00:00Z", counterparty: "电竞训练基地场地服务有限公司", income: "0", expense: "180000.50", summary: "原始银行摘要：场地款", current_purpose: "场地服务", batch_id: "batch-confirmed", batch_filename: initialBatches[0].filename } };
const initialTransactions: Record<string, Transaction[]> = {
  "batch-confirmed": [
    { id: "transaction-1", transacted_at: "2026-10-20T02:30:00Z", income: "1200000.25", expense: "0", balance: "1234567890.99", counterparty: clientName, summary: rawSummary, category: "培训服务", note: "经批准的训练营合同首期服务回款", pm_project_id: null, project_reference: "CC26B10", project_reference_valid: true, status: "confirmed", purpose_correction: null },
    { id: "transaction-2", transacted_at: "2026-10-20T04:00:00Z", income: "0", expense: "180000.50", balance: "1234387890.49", counterparty: initialCorrection.transaction.counterparty, summary: initialCorrection.transaction.summary, category: "场地服务", note: "场地服务", pm_project_id: null, project_reference: "CC26B10", project_reference_valid: true, status: "confirmed", purpose_correction: initialCorrection },
  ],
  "batch-pending": [{ id: "transaction-pending", transacted_at: "2026-10-24T03:10:00Z", income: "25000.25", expense: "0", balance: "1259387890.74", counterparty: "待核验赛事合作公司", summary: "原始附言：服务收入", category: "待确认", note: null, pm_project_id: null, project_reference: "CC26B04", project_reference_valid: true, status: "pending", purpose_correction: null }],
  "batch-other": [],
};
const ledgerItems = [{ id: "ledger-row-1", batch_id: "batch-confirmed", batch_filename: initialBatches[0].filename, transacted_at: "2026-10-20T02:30:00Z", income: "1200000.25", expense: "0", balance: "1234567890.99", counterparty: clientName, summary: rawSummary, note: "训练营项目服务收入", category: "培训服务", project_reference: "CC26B10", bank_serial: "LOCAL-TEST-20261020-001", bank_name: "北京银行", account: "****5678" }];

Object.assign(window, { financeFixtureReads: {
  companyName,
  ledgerItems,
  costCenters: [
    { code: "CC26A01", label: "集团总部管理与运营", group: "A · 总部运营", income: "50000.25", expense: "30000.50", net: "19999.75", transaction_count: 4 },
    { code: "CC26B10", label: "KPL冬季新秀训练营与跨区域人才培养联合交付项目", group: "B · 赛事与培训", income: "1200000.25", expense: "180000.50", net: "1019999.75", transaction_count: 2 },
  ],
} });

function Fixture() {
  const parameters = new URLSearchParams(location.search);
  const role = parameters.get("role") || "finance";
  const [entityId, setEntityId] = useState(entities[0].id);
  const entity = entities.find((item) => item.id === entityId)!;
  const [periodView, setPeriodView] = useState<Props["periodView"]>("realtime");
  const [include, setInclude] = useState(false);
  const [batches, setBatches] = useState(() => parameters.has("long_list") ? [...initialBatches, ...Array.from({ length: 12 }, (_, index): Batch => ({ ...initialBatches[0], id: `history-${index + 1}`, filename: `历史银行流水${index + 1}.xlsx`, row_count: 0 }))] : initialBatches);
  const [transactions, setTransactions] = useState(initialTransactions);
  const [selectedBatch, setSelectedBatch] = useState("");
  const [cashEntries, setCashEntries] = useState<Props["cashEntries"]>([{ id: "cash-1", company: companyName, cash_account: "公司现金", transaction_date: "2026-10-24", direction: "expense", amount: "1500.25", category: "差旅", note: "本地测试现金支出，与银行账户余额独立", pm_project_id: null }]);
  const [obligations, setObligations] = useState<Obligation[]>([obligation, { ...obligation, id: "obligation-project", source: "project", project_id: "project-1", project_no: "CC26B10", project_name: "KPL新秀训练营", amount: "500000", actual_amount: "100000", outstanding_amount: "400000" }, { ...obligation, id: "obligation-payable", direction: "payable", amount: "30000", actual_amount: "0", outstanding_amount: "30000", counterparty: "场地服务公司" }]);
  const [corrections, setCorrections] = useState<Correction[]>([initialCorrection]);
  const [transferItems, setTransferItems] = useState<Props["transfers"]["items"]>([
    { id: "transfer-candidate", transaction_id: "transfer-transaction-candidate", transaction_date: "2026-10-21", source_entity_name: companyName, target_entity_name: entities[1].name, amount: "30000.25", status: "candidate", reason: "similar_group_entity_name", summary: "本地候选内部划转，需财务确认" },
    { id: "transfer-confirmed", transaction_id: "transfer-transaction-confirmed", transaction_date: "2026-10-20", source_entity_name: entities[1].name, target_entity_name: entities[2].name, amount: "20000.50", status: "confirmed", reason: "manual_finance_review", summary: "已人工确认的集团划转" },
  ]);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [lastAction, setLastAction] = useState("");
  const [lastPayload, setLastPayload] = useState<Record<string, FormDataEntryValue>>({});
  const [failNextUpload, setFailNextUpload] = useState(parameters.has("fail_upload"));
  const [failNextSave, setFailNextSave] = useState(parameters.has("fail_save"));
  const canEditBank = role === "finance";
  const canFounder = role === "founder";
  const perform = async (name: string, operation: () => void) => {
    setBusy(name);
    try { await new Promise((resolve) => setTimeout(resolve, 180)); operation(); setLastAction(name); setMessage(`${name} 本地操作已保存`); }
    finally { setBusy(""); }
  };
  const readForm = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget).entries());
    setLastPayload(form);
    return form;
  };
  const bankBalance = entityId === entities[0].id ? "1234567890.99" : "88888.88";
  // Retain old health/transfer/weekly data in the synthetic API payload on
  // purpose: receiving these fields must not revive the retired UI panels.
  const dashboard: Dashboard = {
    confidentiality: "L4", period_start: "2026-10-19", period_end: "2026-10-25", income: include ? "1230000.50" : "1200000.25", expense: "180000.50", net: include ? "1050000.00" : "1019999.75", weekly_top_income: ranks, weekly_top_expense: ranks, anomaly_count: 1, anomalies: [alert], monthly_top_income: ranks, monthly_top_expense: ranks, monthly_anomaly_count: 1, monthly_anomalies: [alert], previous_month: { period_start: "2026-09-01", period_end: "2026-09-30", income: "2000000.25", expense: "1000000.50", net: "999999.75" }, current_year: { period_start: "2026-01-01", period_end: "2026-10-25", income: "12000000.25", expense: "6000000.50", net: "5999999.75" }, bank_balance: bankBalance, cash_balance: "25000.75", total_balance: "1234592891.74", pending_batches: batches.some((item) => item.entity_id === entityId && item.status !== "confirmed"), accounts: [{ company: entity.name, bank_name: entity.default_bank_name, account: "基本户 · ****5678", balance: bankBalance, as_of: "2026-10-24" }], weekly: Array.from({ length: 8 }, (_, index) => ({ year: 2026, week: 35 + index, week_start: `2026-09-${String(index + 1).padStart(2, "0")}`, income: String(10000 + index * 7500), expense: String(index % 2 ? 18000 + index * 7500 : 8000), net: String(index % 2 ? -8000 : 2000 + index * 7500) })), include_internal_transfers: include, fund_health: { data_as_of: "2026-10-24", freshness_days: 1, freshness_status: "fresh", minimum_balance: { amount: "500000.25", date: "2026-10-01", account_count: 1, covered_account_count: 1, coverage_complete: true }, maximum_daily_net_outflow: { amount: "80000.25", date: "2026-10-15", net: "-80000.25" }, average_weekly_net_inflow_4w: { amount: "30000.25", period_start: "2026-10-01", period_end: "2026-10-25", weeks: [] }, top3_income_concentration: { amount: "900000", total: "1200000", ratio: 0.75, parties: ranks }, top3_expense_concentration: { amount: "90000", total: "180000", ratio: 0.5, parties: ranks }, unclassified: { amount: "5000.25", count: 2, income: "0", expense: "5000.25" }, internal_transfers: { gross_amount: "20000.50", count: 1, income: "20000.50", expense: "20000.50", auto_count: 0, manual_count: 1 } }, receivables_payables: Object.fromEntries(["receivable", "payable"].map((direction) => { const items = obligations.filter((item) => item.direction === direction); return [direction, { total: items.reduce((sum, item) => sum + Number(item.outstanding_amount), 0), count: items.length, items }]; })) as Dashboard["receivables_payables"],
  };
  const annualYear = periodView === "realtime" ? 2026 : periodView;
  const annual: Annual = {
    confidentiality: "L4", entity_id: entityId, entity_name: entity.name, year: annualYear, period_start: `${annualYear}-01-01`, period_end: `${annualYear}-12-31`, confirmed_only: true, include_internal_transfers: include, coverage: { data_complete: false, confirmed_period_start: `${annualYear}-01-01`, confirmed_period_end: `${annualYear}-10-24`, confirmed_batch_count: 1, pending_batch_count: 1, pending_batches: [{ id: "batch-pending", filename: initialBatches[1].filename, period_start: "2026-10-20", period_end: "2026-10-24", status: "pending" }] }, income: "12000000.25", expense: "6000000.50", net: "5999999.75", opening_balance: "1000000.25", closing_balance: bankBalance, balance_change: "5999999.75", transaction_count: 26, income_transaction_count: 14, expense_transaction_count: 12, average_income: "857142.875", average_expense: "500000.04", largest_income: "1200000.25", largest_expense: "800000.50", counterparty_count: 8, monthly: Array.from({ length: 12 }, (_, index) => ({ month: index + 1, income: String((index + 1) * 100000), expense: String((index + 1) * 50000), net: String((index + 1) * 50000), transaction_count: index + 1 })), top_income: ranks, top_expense: ranks, income_concentration: { amount: "9000000", total: "12000000", ratio: 0.75, parties: ranks }, expense_concentration: { amount: "3000000", total: "6000000", ratio: 0.5, parties: ranks }, income_categories: [{ name: "跨区域赛事和训练服务合同回款", amount: "12000000.25", transaction_count: 14, ratio: 1 }], expense_categories: [{ name: "赛事运营场地、人员及设备服务费用", amount: "6000000.50", transaction_count: 12, ratio: 1 }], largest_outflow_days: [{ date: "2026-10-15", income: "0", expense: "80000.25", net: "-80000.25", transaction_count: 3 }], anomaly_count: 1, anomalies: [alert], unclassified: { count: 2, amount: "5000.25", ratio: 0.1 }, internal_transfers: { count: 1, income: "20000.50", expense: "20000.50" },
  };
  const transferRegistry: Props["transfers"] = { items: transferItems, confirmed_count: transferItems.filter((item) => item.status === "confirmed").length, candidate_count: transferItems.filter((item) => item.status === "candidate").length, confirmed_amount: transferItems.filter((item) => item.status === "confirmed").reduce((sum, item) => sum + Number(item.amount), 0), candidate_amount: transferItems.filter((item) => item.status === "candidate").reduce((sum, item) => sum + Number(item.amount), 0) };
  const correctionRegistry: Props["purposeCorrections"] = { items: corrections, pending_count: corrections.filter((item) => item.status === "pending").length, approved_count: corrections.filter((item) => item.status === "approved").length, rejected_count: corrections.filter((item) => item.status === "rejected").length };
  const workspace = <FinanceWorkspace token="local-fixture-only" user={{ id: `user-${role}`, username: canFounder ? "founder" : role, display_name: `测试${role}`, role: canFounder ? "founder" : "employee", organization_role: canFounder ? "management" : role === "viewer" ? "management" : "finance", confidentiality_ceiling: canFounder ? "L5" : "L4", departments: [] }} entity={entity} entities={entities} dashboard={parameters.has("loading") ? null : dashboard} periodView={periodView} annualYears={[2026, 2025]} annualDashboard={annual} batches={batches.filter((item) => item.entity_id === entityId)} cashEntries={cashEntries} transfers={transferRegistry} purposeCorrections={correctionRegistry} includeInternalTransfers={include} selectedBatch={selectedBatch} transactions={transactions[selectedBatch] || []} busy={parameters.has("loading") ? "company" : busy} message={message} uploadError="" canEditBank={canEditBank} canDeleteConfirmedBatch={canFounder} canReviewPurposeCorrections={canFounder} canEditCash={canEditBank || canFounder} projects={[]}
    onEntitySelect={(id) => { setEntityId(id); setSelectedBatch(""); }}
    onPeriodViewChange={setPeriodView} onTransferScopeChange={setInclude}
    onTransferDecision={async (id, action) => perform(`transfer-${action}-${id}`, () => setTransferItems((items) => items.map((item) => item.transaction_id === id || item.id === id ? { ...item, status: action === "confirm" ? "confirmed" : action === "reject" ? "rejected" : "candidate" } : item)))}
    onReceivablePayableCreate={async (event) => { const form = readForm(event); await perform("receivable-payable-create", () => setObligations((items) => [...items, { ...obligation, id: "obligation-created", direction: String(form.direction) as "receivable" | "payable", due_date: String(form.due_date), amount: String(form.amount), actual_amount: String(form.actual_amount), outstanding_amount: String(Number(form.amount) - Number(form.actual_amount)), counterparty: String(form.counterparty), note: String(form.note), overdue: false }])); }}
    onReceivablePayableUpdate={async (event, id) => { const form = readForm(event); await perform(`receivable-payable-${id}`, () => setObligations((items) => items.map((item) => item.id === id ? { ...item, amount: String(form.amount), actual_amount: String(form.actual_amount), note: String(form.note) } : item))); }}
    onUpload={async (event) => { const form = readForm(event); if (failNextUpload) { setFailNextUpload(false); await perform("upload", () => { throw new Error("本地测试：流水文件暂时无法导入，请重试"); }); return; } await perform("upload", () => { setBatches((items) => [...items, { ...initialBatches[1], id: "batch-uploaded", filename: form.file instanceof File ? form.file.name : "本地上传.csv", row_count: 1 }]); setTransactions((state) => ({ ...state, "batch-uploaded": [{ ...initialTransactions["batch-pending"][0], id: "uploaded-transaction" }] })); setSelectedBatch("batch-uploaded"); }); }}
    onCashEntry={async (event) => { const form = readForm(event); await perform("cash", () => setCashEntries((items) => [...items, { id: "cash-created", company: entity.name, cash_account: String(form.cash_account), transaction_date: String(form.transaction_date), direction: String(form.direction) as "income" | "expense" | "opening", amount: String(form.amount), category: String(form.category), note: String(form.note), pm_project_id: null }])); }}
    onSelectBatch={async (id) => { await perform(`batch-${id}`, () => setSelectedBatch(id)); }}
    onConfirmBatch={async (id) => { await perform(`confirm-${id}`, () => setBatches((items) => items.map((item) => item.id === id ? { ...item, status: "confirmed", confirmer: "测试财务", confirmed_at: "2026-10-25T08:00:00Z" } : item))); }}
    onDeleteBatch={async (batch) => { if (!window.confirm(`确认删除 ${batch.filename}？`)) return; await perform(`delete-${batch.id}`, () => { setBatches((items) => items.filter((item) => item.id !== batch.id)); if (selectedBatch === batch.id) setSelectedBatch(""); }); }}
    onUpdateTransaction={async (event, id) => { const form = readForm(event); if (failNextSave) { setFailNextSave(false); await perform(`transaction-${id}`, () => { throw new Error("本地测试：分类保存失败，请重试"); }); return; } await perform(`transaction-${id}`, () => setTransactions((state) => ({ ...state, [selectedBatch]: state[selectedBatch].map((item) => item.id === id ? { ...item, category: String(form.category), project_reference: String(form.project_reference), pm_project_id: String(form.pm_project_id) || null, ...(form.annotation_only === "true" ? {} : { counterparty: String(form.counterparty), transacted_at: String(form.transacted_at) }) } : item) }))); }}
    onPurposeCorrectionRequest={async (event, id) => { const form = readForm(event); const transaction = transactions[selectedBatch].find((item) => item.id === id)!; const correction: Correction = { ...initialCorrection, id: "correction-created", transaction_id: id, previous_purpose: transaction.note, proposed_purpose: String(form.proposed_purpose), transaction: { ...initialCorrection.transaction, counterparty: transaction.counterparty, income: transaction.income, expense: transaction.expense, summary: transaction.summary, current_purpose: transaction.note } }; await perform(`purpose-request-${id}`, () => { setCorrections((items) => [correction, ...items]); setTransactions((state) => ({ ...state, [selectedBatch]: state[selectedBatch].map((item) => item.id === id ? { ...item, purpose_correction: correction } : item) })); }); }}
    onPurposeCorrectionReview={async (id, decision) => perform(`purpose-review-${id}`, () => setCorrections((items) => items.map((item) => item.id === id ? { ...item, status: decision === "approve" ? "approved" : "rejected", reviewed_by: "测试创始人", reviewed_at: "2026-10-25T08:00:00Z" } : item)))}
  />;
  const outputs = <><output data-testid="last-action" hidden>{lastAction}</output><output data-testid="last-payload" hidden>{JSON.stringify(lastPayload)}</output><output data-testid="selected-batch" hidden>{selectedBatch}</output><output data-testid="bank-balance" hidden>{bankBalance}</output><output data-testid="scope" hidden>{include ? "including" : "excluding"}</output></>;
  if (parameters.has("shell")) return <main className="shell"><aside className="sidebar" aria-label="桌面主导航"><span>JAOS</span></aside><section className="content"><header className="topbar"><div><p className="eyebrow">JAOS</p><h1>财务分析</h1></div></header>{workspace}<footer><span>JAOS · 财务界面本地验证</span></footer>{outputs}</section><nav className="mobileTabbar" aria-label="手机主导航">{["工作台", "AI资料检索", "智能创作", "资料上传", "更多"].map((name) => <button type="button" key={name}><span className="mobileTabIcon" aria-hidden="true">◇</span><span>{name}</span></button>)}</nav></main>;
  return <main style={{ padding: 24, maxWidth: 1600, margin: "0 auto" }}>{workspace}{outputs}</main>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
