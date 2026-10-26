import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { WorkspaceSidebar, WorkspaceMobileNavigation, type WorkspaceNavigationProps } from "../app/workspace-navigation";
import "../app/globals.css";
import "../app/project-management.css";
import "../app/finance-workspace.css";
import "../app/workspace-navigation.css";

// Real navigation with synthetic local state. This fixture has no token,
// network requests, credentials or production business data.
type Props = WorkspaceNavigationProps;
const tabs: Props["visibleTabs"] = [
  "工作台", "财务分析", "项目管理", "资料上传", "合同档案库", "AI资料检索", "智能创作", "入库审核", "资料治理", "系统状态", "账号管理",
].map((name) => ({ name: name as Props["active"] }));
const restricted = ["工作台", "资料上传", "AI资料检索", "智能创作"];
const entities: Props["financeEntities"] = [
  { id: "entity-jingao", display_name: "京奥电竞", business_name: "集团总部与电竞赛事运营" },
  { id: "entity-ace", display_name: "王牌猎豹", business_name: "JAG三角洲国际赛事与青训" },
  { id: "entity-power", display_name: "劲腾豹跃", business_name: "JAG王者荣耀俱乐部" },
  { id: "entity-xingyao", display_name: "星曜电竞", business_name: "电竞教育与场馆运营" },
];

function Fixture() {
  const parameters = new URLSearchParams(location.search);
  const [active, setActive] = useState<Props["active"]>(parameters.has("finance") ? "财务分析" : "工作台");
  const [selectedEntity, setSelectedEntity] = useState(entities[0].id);
  const [lastAction, setLastAction] = useState("");
  const isRestricted = parameters.has("restricted");
  const financeEntities = parameters.has("empty_entities") || isRestricted ? [] : parameters.has("long_names")
    ? entities.map((entity, index) => index === 0 ? { ...entity, display_name: "京奥电竞跨区域赛事运营与青训联合发展事业部", business_name: "集团总部与国际电竞赛事运营及联合人才培养业务" } : entity)
    : entities;
  const props: Props = {
    active,
    visibleTabs: isRestricted ? tabs.filter((tab) => restricted.includes(tab.name)) : tabs,
    financeEntities,
    selectedFinanceEntityId: selectedEntity,
    reviewCount: parameters.has("zero_reviews") ? 0 : 128,
    outboundEnabled: parameters.get("outbound") === "1",
    user: { name: parameters.has("long_names") ? "跨区域电竞赛事与青训联合管理负责人" : "创始人", roleLabel: isRestricted ? "业务" : "管理", levelLabel: isRestricted ? "L2 · 业务普通资料" : "L5 · 公司最高机密" },
    onNavigate: (tab) => { setActive(tab); setLastAction(`navigate:${tab}`); },
    onEntitySelect: (id) => { setSelectedEntity(id); setActive("财务分析"); setLastAction(`entity:${id}`); },
    onPasswordChange: () => setLastAction("password"),
    onLogout: () => setLastAction("logout"),
  };
  return (
    <main className="shell workspaceShell">
      <WorkspaceSidebar {...props} />
      <section className="content">
        <header className="topbar"><div><p className="eyebrow">京奥AI智能运营系统 · JAOS</p><h1>{active}</h1></div><span className="systemState"><i />本地测试环境</span></header>
        <section className="navigationFixtureWelcome"><span>WORKSPACE</span><h2>每一项工作，都井然有序。</h2><p>从左侧导航进入业务与知识协作，快速找到所需功能。</p></section>
        <section className="navigationFixtureMetrics"><article><span>进行中项目</span><strong>12</strong><small>项目协作与进度跟踪</small></article><article><span>待确认事项</span><strong>8</strong><small>今天需要关注的工作</small></article><article><span>知识资料</span><strong>268</strong><small>保留原始文件与引用</small></article></section>
        <section className="navigationFixtureTasks"><h2>工作概览</h2><p>所有示例信息均为本地测试数据。</p>{["项目交付与预算核对", "银行流水与用途复核", "知识资料整理与审核"].map((name, index) => <article key={name}><span>0{index + 1}</span><strong>{name}</strong><small>待处理</small></article>)}</section>
        <div className="navigationFixtureOutput"><span data-testid="last-action">{lastAction}</span><span data-testid="current-entity">{selectedEntity}</span></div>
        <style>{`
          .navigationFixtureWelcome { padding: 32px; border: 1px solid #dce5ef; border-radius: 16px; background: linear-gradient(120deg,#fff,#edf4fd); }
          .navigationFixtureWelcome > span { color: #4875ae; font-size: 11px; letter-spacing: 2px; font-weight: 800; }
          .navigationFixtureWelcome h2 { margin: 15px 0 12px; font-size: 28px; color: #213650; }
          .navigationFixtureWelcome p { margin: 0; color: #77869a; font-size: 14px; line-height: 1.7; }
          .navigationFixtureMetrics { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 16px; margin: 20px 0; }
          .navigationFixtureMetrics article { display: grid; gap: 12px; padding: 24px; border-radius: 14px; border: 1px solid #e0e6ee; background: #fff; }
          .navigationFixtureMetrics span { color: #6d7e95; font-size: 13px; }
          .navigationFixtureMetrics strong { color: #273d5a; font-size: 32px; }
          .navigationFixtureMetrics small { color: #8b98aa; }
          .navigationFixtureTasks { padding: 24px; border: 1px solid #e0e6ee; border-radius: 14px; background: #fff; }
          .navigationFixtureTasks h2 { margin: 0; font-size: 18px; }
          .navigationFixtureTasks > p { color: #8995a7; font-size: 13px; }
          .navigationFixtureTasks article { display: flex; align-items: center; gap: 16px; padding: 22px 0; border-top: 1px solid #edf0f5; }
          .navigationFixtureTasks article > span { color: #91a1b8; font-size: 13px; }
          .navigationFixtureTasks article > strong { flex: 1; min-width: 0; color: #4a5e79; font-size: 14px; }
          .navigationFixtureTasks article > small { color: #537bad; font-size: 12px; }
          .navigationFixtureOutput { margin-top: 900px; display: flex; flex-wrap: wrap; gap: 16px; color: #7d8a9e; font-size: 11px; }
          @media(max-width:760px) { .navigationFixtureWelcome { padding: 22px; } .navigationFixtureWelcome h2 { font-size: 23px; } .navigationFixtureMetrics { grid-template-columns: 1fr; gap: 10px; } .navigationFixtureMetrics article { padding: 18px; } }
        `}</style>
      </section>
      <WorkspaceMobileNavigation {...props} />
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<Fixture />);
