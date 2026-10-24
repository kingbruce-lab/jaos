import React, { type ComponentProps, type FormEvent, useState } from "react";
import { createRoot } from "react-dom/client";
import { ProjectManagementWorkspace } from "../app/page";
import "../app/globals.css";
import "../app/project-management.css";

// Uses the real workspace without network requests, production accounts or data.
type WorkspaceProps = ComponentProps<typeof ProjectManagementWorkspace>;
type Project = NonNullable<WorkspaceProps["selected"]>;

const primaryProject: Project = {
  id: "project-alpha",
  project_no: "CC26B10",
  name: "2026KPL冬季新秀训练营与跨区域电竞人才培养联合交付项目",
  company_name: "京奥电竞（北京）科技有限公司",
  client: "天竞华娱（苏州）文化传播有限公司与联合赛事运营事业部",
  client_contact: "郑",
  business_category: "电竞培训",
  manager: "观棋",
  manager_user_id: "owner-1",
  members: ["观棋", "郑睿", "高亚凡", "窦郝燕"],
  collaborators: [{ user_id: "collaborator-1", username: "colleague", display_name: "协作同事" }],
  planned_start: "2026-10-01",
  planned_end: "2026-12-31",
  objective: "开展新秀训练营，完成训练组织、跨区域协同与项目交付。",
  contract_document_id: "contract-alpha",
  contract_status: "unsigned",
  contract_alert: true,
  contract_alert_message: "项目已进入执行，请完成合同签署并确认收件。",
  contract_amount: "2200000.00",
  budget_revenue: "2200000.00",
  budget_cost: "1750000.00",
  budget_tax: "132000.00",
  expected_margin: "318000.00",
  process_received: "12000.00",
  process_spent: "8000.00",
  process_advanced: "1000.00",
  process_finance_updated_at: "2026-10-24T08:00:00Z",
  bank_received: "10000.00",
  bank_spent: "7000.00",
  bank_transaction_count: 2,
  status: "active",
  progress_percent: 25,
  current_stage: "训练营筹备",
  proposal_attached: true,
  closing_report_attached: false,
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-10-24T08:00:00Z",
  cashflow_plans: [{ id: "cashflow-1", direction: "receivable", due_date: "2026-11-01", amount: "500000.00", counterparty: "测试甲方", note: "首期回款", actual_amount: "10000.00", actual_date: "2026-10-20", running_cash: "500000.00" }],
  maximum_funding_gap: "50000.00",
  progress_updates: [{ id: "progress-1", progress_percent: 25, current_stage: "训练营筹备", completed: "已完成场地和人员筹备", next_step: "开始集中训练", risks: null, needs_coordination: false, creator: "观棋", created_at: "2026-10-24T08:00:00Z" }],
  initiation_reviews: [{ slot: "founder", label: "创始人复核", decision: "approved", note: "同意立项", reviewer: "测试负责人", decided_at: "2026-09-30T08:00:00Z" }],
  closing_reviews: [],
  planned_receivable: "500000.00",
  received_amount: "10000.00",
  outstanding_receivable: "490000.00",
  payment_complete: false,
  portfolio_group: "ongoing",
};

const initialProjects: Project[] = [
  primaryProject,
  { ...primaryProject, id: "project-beta", project_no: "CC26B04", name: "2026英雄联盟无畏新生试炼场", client: "腾竞体育文化发展（上海）有限公司", manager: "高亚凡", manager_user_id: "owner-2", contract_status: "signed_received", contract_alert: false, progress_percent: 80 },
  { ...primaryProject, id: "project-draft", project_no: "CC25A01", name: "2025电竞场馆立项准备项目", manager: "高亚凡", manager_user_id: "owner-2", status: "draft", planned_start: "2025-10-01", planned_end: "2025-12-31", created_at: "2025-09-01T08:00:00Z", portfolio_group: "pipeline", contract_alert: false },
  { ...primaryProject, id: "project-unpaid", project_no: "CC26C01", name: "结案待回款示例项目", status: "closed", portfolio_group: "closed_unpaid", progress_percent: 100, closing_summary: "交付完成，继续跟踪剩余回款。", actual_revenue: "20000.00", actual_cost: "10000.00", actual_receivable: "1000.00", actual_payable: "0.00", outstanding_receivable: "1000.00" },
  { ...primaryProject, id: "project-archive", project_no: "CC24A02", name: "2024已归档历史赛事项目", status: "archived", planned_start: "2024-10-01", planned_end: "2024-12-31", portfolio_group: "archived", progress_percent: 100, contract_status: "signed_received", contract_alert: false, payment_complete: true, outstanding_receivable: "0.00" },
  ...Array.from({ length: 12 }, (_, index): Project => ({ ...primaryProject, id: `project-extra-${index}`, project_no: `CC26A${String(index + 1).padStart(2, "0")}`, name: `区域赛事运营与青训项目 ${index + 1}`, manager: index % 2 ? "高亚凡" : "观棋", manager_user_id: index % 2 ? "owner-2" : "owner-1", contract_status: "signed_received", contract_alert: false })),
];

function Fixture() {
  const parameters = new URLSearchParams(location.search);
  const founder = parameters.has("founder");
  const viewer = parameters.has("viewer");
  const mobileShell = parameters.has("mobile_shell");
  const [projects, setProjects] = useState(() => parameters.has("large_amounts")
    ? initialProjects.map((project) => ({ ...project, contract_amount: "1234567890.99", expected_margin: "234567890.12", process_advanced: "123456789.01" }))
    : initialProjects);
  const [selected, setSelected] = useState<Project | null>(null);
  const [message, setMessage] = useState("");
  const [selectCount, setSelectCount] = useState(0);
  const [lastUpdatedContract, setLastUpdatedContract] = useState("");
  const [busy, setBusy] = useState("");
  const [createdProjectName, setCreatedProjectName] = useState("");
  const [failNextSelection, setFailNextSelection] = useState(parameters.has("fail"));
  const user: WorkspaceProps["user"] = {
    id: founder ? "founder-1" : viewer ? "viewer-1" : "owner-1",
    username: founder ? "founder" : viewer ? "viewer" : "manager",
    display_name: founder ? "测试创始人" : viewer ? "只读同事" : "观棋",
    role: founder ? "founder" : "employee",
    organization_role: founder ? "management" : "business",
    confidentiality_ceiling: founder ? "L5" : "L3",
    departments: ["training"],
  };
  const update = (changes: Partial<Project>) => {
    setSelected((current) => current ? { ...current, ...changes } : current);
    setProjects((items) => items.map((item) => item.id === selected?.id ? { ...item, ...changes } : item));
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage("本地测试操作已保存");
  };
  const groupCounts = Object.fromEntries(["ongoing", "closed_unpaid", "pipeline", "ready_archive", "archived"].map((group) => [group, projects.filter((project) => project.portfolio_group === group).length]));
  const contentWidth = Number(parameters.get("content_width")) || 1552;
  const workspace = <ProjectManagementWorkspace
      user={user}
      registry={{ items: projects, counts: {}, portfolio_counts: groupCounts }}
      selected={selected}
      collaboratorCandidates={[{ user_id: "colleague-2", username: "assistant", display_name: "新增协作同事" }]}
      busy={busy}
      message={message}
      canCreate={!viewer && !founder}
      canReview={founder}
      canArchive={founder}
      canFinanceConfirm={founder}
      deletePasswordConfigured={true}
      onCreate={async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const project: Project = { ...primaryProject,
          id: "project-created", project_no: String(form.get("project_no")), name: String(form.get("name")),
          client: String(form.get("client")), company_name: String(form.get("company_name")),
          client_contact: String(form.get("client_contact")), business_category: String(form.get("business_category")),
          planned_start: String(form.get("planned_start")), planned_end: String(form.get("planned_end")),
          objective: String(form.get("objective")), status: "draft", portfolio_group: "pipeline", contract_alert: false,
        };
        setBusy("create");
        try {
          await new Promise((resolve) => setTimeout(resolve, 150));
          setProjects((items) => [...items, project]);
          setCreatedProjectName(project.name);
          setMessage("项目草稿已建立");
        } finally {
          setBusy("");
        }
      }}
      onUpdate={async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const contractStatus = form.get("contract_status") as "unsigned" | "signed_received";
        setBusy("project-update");
        try {
          await new Promise((resolve) => setTimeout(resolve, 800));
          setLastUpdatedContract(contractStatus);
          update({ name: String(form.get("name")), client_contact: String(form.get("client_contact")), contract_status: contractStatus });
        } finally {
          setBusy("");
        }
      }}
      onCollaborators={async (usernames) => update({ collaborators: usernames.map((username) => ({ user_id: username === "colleague" ? "collaborator-1" : "colleague-2", username, display_name: username === "colleague" ? "协作同事" : "新增协作同事" })) })}
      onContractStatus={async (event) => { event.preventDefault(); const status = new FormData(event.currentTarget).get("contract_status") as "unsigned" | "signed_received"; update({ contract_status: status, contract_alert: status !== "signed_received" }); }}
      onProcessFinance={submit}
      onRequestDeletion={submit}
      onDeletionDecision={submit}
      onConfigureDeletePassword={submit}
      onFounderDelete={submit}
      onArchive={async () => undefined}
      onSelect={async (id) => {
        setSelectCount((count) => count + 1);
        await new Promise((resolve) => setTimeout(resolve, 150));
        if (failNextSelection) {
          setFailNextSelection(false);
          throw new Error("项目暂时无法加载，请重试");
        }
        setSelected(projects.find((project) => project.id === id) || null);
      }}
      onCashflow={submit}
      onCashflowUpdate={async (id, values) => update({ cashflow_plans: selected?.cashflow_plans?.map((plan) => plan.id === id ? { ...plan, ...values, direction: values.direction as "receivable" | "payable" } : plan) })}
      onCashflowActual={submit}
      onSubmitInitiation={async () => undefined}
      onProgress={async (event) => { event.preventDefault(); const form = new FormData(event.currentTarget); update({ progress_percent: Number(form.get("progress_percent")), current_stage: String(form.get("current_stage")) }); setMessage("项目进度已更新"); }}
      onSubmitClosing={submit}
      onReview={submit}
    />;
  const outputs = <>
    <output data-testid="selection-count" hidden>{selectCount}</output>
    <output data-testid="selected-id" hidden>{selected?.id || ""}</output>
    <output data-testid="updated-contract-status" hidden>{lastUpdatedContract}</output>
    <output data-testid="created-project-name" hidden>{createdProjectName}</output>
  </>;
  if (mobileShell) return <main className="shell">
    <aside className="sidebar" aria-label="桌面导航"><span>JAOS</span></aside>
    <section className="content">
      <header className="topbar"><div><p className="eyebrow">JAOS</p><h1>项目管理</h1></div></header>
      {workspace}
      <footer><span>JAOS · 本地界面验证</span></footer>
      {outputs}
    </section>
    <nav className="mobileTabbar" aria-label="手机主导航">{["工作台", "AI资料检索", "智能创作", "资料上传", "更多"].map((name) => <button type="button" key={name}><span className="mobileTabIcon" aria-hidden="true">◇</span><span>{name}</span></button>)}</nav>
  </main>;
  return <main style={{ padding: "24px", maxWidth: contentWidth + 48, margin: "0 auto" }}>{workspace}{outputs}</main>;
}

createRoot(document.getElementById("root")!).render(<Fixture />);
