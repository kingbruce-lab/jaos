import React, { useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import Home from "../app/page";
import { WorkspaceHome, type WorkspaceHomeProps } from "../app/workspace-home";
import { WorkspaceSidebar, WorkspaceMobileNavigation, type WorkspaceNavigationProps } from "../app/workspace-navigation";
import "../app/globals.css";
import "../app/project-management.css";
import "../app/finance-workspace.css";
import "../app/workspace-navigation.css";
import "../app/workspace-home.css";

// Real home and navigation components, synthetic local state only. No token,
// production account, business file or API is used by this fixture.
type HomeProps = WorkspaceHomeProps;
type NavigationProps = WorkspaceNavigationProps;
const tabs: NavigationProps["visibleTabs"] = ["工作台", "财务分析", "项目管理", "资料上传", "合同档案库", "AI资料检索", "智能创作", "入库审核", "资料治理", "系统状态", "账号管理"].map((name) => ({ name: name as NavigationProps["active"] }));
const employeeTabs = ["工作台", "项目管理", "资料上传", "AI资料检索", "智能创作"];
const projects: HomeProps["projects"] = [
  { id: "home-project-1", name: "2026KPL冬季新秀训练营与跨区域电竞人才培养联合交付项目", client: "本地示例文化传播与赛事运营有限公司", year: 2026, domain: "training", knowledge_status: "approved", document_count: 17, closing_report_reminder: false },
  { id: "home-project-2", name: "2026城市电竞公开赛执行与联合运营方案", client: "本地示例体育文化有限公司", year: 2026, domain: "tournament", knowledge_status: "candidate", document_count: 8, closing_report_reminder: true },
  { id: "home-project-3", name: "公司介绍与业务能力资料", client: null, year: null, domain: "company", knowledge_status: "current", document_count: 2, closing_report_reminder: false },
  { id: "home-project-4", name: "AI创作与电竞课程培训资料", client: null, year: 2025, domain: "training", knowledge_status: "approved", document_count: 12, closing_report_reminder: false },
  { id: "home-project-5", name: "区域赛事运营复盘及结案资料", client: "本地示例运营公司", year: 2025, domain: "tournament", knowledge_status: "superseded", document_count: 2, closing_report_reminder: false },
  { id: "home-project-6", name: "不应出现在前五条中的历史项目", client: null, year: 2024, domain: "venue", knowledge_status: "approved", document_count: 10, closing_report_reminder: false },
];
const entities: NavigationProps["financeEntities"] = [
  { id: "home-entity-jingao", display_name: "京奥电竞", business_name: "集团总部与电竞赛事运营" },
  { id: "home-entity-ace", display_name: "王牌猎豹", business_name: "JAG三角洲国际赛事与青训" },
  { id: "home-entity-power", display_name: "劲腾豹跃", business_name: "JAG王者荣耀俱乐部" },
  { id: "home-entity-xingyao", display_name: "星曜电竞", business_name: "电竞教育与场馆运营" },
];

function Fixture() {
  const parameters = new URLSearchParams(location.search);
  const employee = parameters.has("employee");
  const reviewer = parameters.has("reviewer");
  const [active, setActive] = useState<NavigationProps["active"]>("工作台");
  const [question, setQuestion] = useState(parameters.get("query") || "");
  const [searching, setSearching] = useState(parameters.has("busy"));
  const [submittedQuery, setSubmittedQuery] = useState(parameters.has("result") || parameters.has("busy") ? "旧检索问题" : "");
  const [hasResult, setHasResult] = useState(parameters.has("result") || parameters.has("busy"));
  const [lastAction, setLastAction] = useState("");
  const [searchCount, setSearchCount] = useState(0);
  const [requestedQuery, setRequestedQuery] = useState("");
  const [error, setError] = useState("");
  const searchResultRef = useRef<HTMLDivElement | null>(null);
  const visibleProjects = parameters.has("empty") ? [] : parameters.has("long_names") ? projects.map((project, index) => index ? project : { ...project, name: "2026跨区域国际电竞赛事运营与青训人才培养联合交付和数字知识协同管理完整资料项目", client: "本地示例跨区域联合管理与国际体育文化传播有限公司" }) : projects;
  const counts: HomeProps["counts"] = parameters.has("loading") ? null : parameters.has("unknown_counts") ? { documents: null, source_available_documents: null, current_documents: null } : parameters.has("zero_counts") ? { documents: 0, source_available_documents: 0, current_documents: 0 } : parameters.has("large_counts") ? { documents: 1234567890, source_available_documents: 1098765432, current_documents: 123456789 } : { documents: 5184, source_available_documents: 5088, current_documents: 1 };

  function navigate(tab: NavigationProps["active"]) { setActive(tab); setLastAction(`navigate:${tab}`); }
  async function search(query: string) {
    const value = query.trim();
    if (!value || searching) return;
    setSearching(true);
    setError("");
    setRequestedQuery(value);
    setSearchCount((current) => current + 1);
    setLastAction(`search:${value}`);
    await new Promise((resolve) => setTimeout(resolve, 450));
    if (value === "失败测试") { setError("本地测试：检索暂时不可用，请保留问题并重试。"); setHasResult(false); }
    else { setSubmittedQuery(value); setHasResult(true); }
    setSearching(false);
  }
  const navigation: NavigationProps = {
    active,
    visibleTabs: employee ? tabs.filter((tab) => employeeTabs.includes(tab.name)) : reviewer ? tabs.filter((tab) => tab.name !== "账号管理") : tabs,
    financeEntities: employee ? [] : entities,
    selectedFinanceEntityId: entities[0].id,
    reviewCount: employee ? 0 : 128,
    outboundEnabled: false,
    user: { name: parameters.has("long_names") ? "跨区域电竞赛事与青训联合管理负责人" : employee ? "示例业务同事" : reviewer ? "示例资料管理员" : "创始人", roleLabel: employee ? "业务" : "管理", levelLabel: employee ? "L2 · 业务普通资料" : "L5 · 公司最高机密" },
    onNavigate: navigate,
    onEntitySelect: (id) => { setActive("财务分析"); setLastAction(`entity:${id}`); },
    onPasswordChange: () => setLastAction("password"),
    onLogout: () => setLastAction("logout"),
  };
  const home: HomeProps = {
    question,
    onQuestionChange: setQuestion,
    onSearch: () => search(question),
    searching,
    searchResult: hasResult ? <div className="compactAnswer"><strong data-testid="search-answer">已根据“{submittedQuery}”找到本地示例资料，引用保留原始文件和页码。</strong><span>历史资料检索 · 本地证据结果 · 3 份相关资料</span></div> : null,
    searchResultRef,
    submittedQuery,
    resultCount: hasResult ? 3 : null,
    counts,
    projects: visibleProjects,
    categoryNames: { training: "电竞培训", tournament: "电竞赛事", company: "公司资料", venue: "场馆运营" },
    canReview: !employee,
    canViewLibraryTotals: !employee && !reviewer,
    reviewCount: parameters.has("zero_reviews") ? 0 : 128,
    onNavigate: navigate,
    onProjectSearch: (query) => { setQuestion(query); return search(query); },
  };
  return (
    <main className="shell workspaceShell">
      <WorkspaceSidebar {...navigation} />
      <section className="content">
        <header className="topbar homeTopbar"><div><p className="eyebrow">京奥AI智能运营系统 · JAOS</p><h1>{active}</h1></div><div className="topActions"><span className="systemState"><i /> 本地预览</span><button type="button" className="primaryButton" onClick={() => navigate(employee ? "资料上传" : "入库审核")}>{employee ? "上传资料" : "查看入库队列"}</button></div></header>
        {error && <div className="globalError" role="alert">{error}<button type="button" aria-label="关闭错误提示" onClick={() => setError("")}>×</button></div>}
        {active === "工作台" ? <WorkspaceHome {...home} /> : <section className="homeFixtureDestination"><h2>{active}</h2><p>本地示例操作已记录，未请求真实服务。</p><button type="button" onClick={() => setActive("工作台")}>返回工作台</button></section>}
        <footer><span>工作台预览仅使用本地示例数据</span></footer>
        <div className="homeFixtureOutputs" aria-hidden="true"><span data-testid="last-action">{lastAction}</span><span data-testid="search-count">{searchCount}</span><span data-testid="requested-query">{requestedQuery}</span></div>
      </section>
      <WorkspaceMobileNavigation {...navigation} />
      <style>{`.homeFixtureOutputs { display:none; } .homeFixtureDestination { padding:32px; border:1px solid #dfe7f0; border-radius:14px; background:#fff; } .homeFixtureDestination > button { min-height:44px; padding:10px 18px; border:1px solid #bed0e8; border-radius:8px; background:#edf4ff; color:#285995; }`}</style>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(new URLSearchParams(location.search).has("actual_home") ? <Home /> : <Fixture />);
