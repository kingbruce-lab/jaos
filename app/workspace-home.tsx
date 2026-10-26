"use client";

import { useRef, type ComponentProps, type ReactNode, type RefObject } from "react";
import { NavigationIcon, type NavigationTab } from "./workspace-navigation";

export type WorkspaceHomeProps = {
  question: string;
  onQuestionChange: (value: string) => void;
  onSearch: () => void | Promise<void>;
  searching: boolean;
  searchResult: ReactNode | null;
  searchResultRef?: RefObject<HTMLDivElement | null>;
  submittedQuery: string;
  resultCount: number | null;
  counts: {
    documents: number | null;
    source_available_documents: number | null;
    current_documents: number | null;
  } | null;
  projects: {
    id: string;
    name: string;
    client: string | null;
    year: number | null;
    domain: string;
    knowledge_status: string;
    document_count: number;
    closing_report_reminder: boolean;
  }[];
  categoryNames: Record<string, string>;
  canReview: boolean;
  canViewLibraryTotals: boolean;
  reviewCount: number;
  onNavigate: (tab: NavigationTab) => void;
  onProjectSearch: (query: string) => void | Promise<void>;
};

type HomeMetric = {
  label: string;
  value: number | null | undefined;
  note: string;
  tone: string;
  icon: ComponentProps<typeof NavigationIcon>["name"];
};

const formatCount = (value: number | null | undefined) => value === null || value === undefined || !Number.isFinite(value) ? "—" : new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
const knowledgeLabels: Record<string, string> = { candidate: "候选资料", approved: "已入库", current: "当前版本", superseded: "历史版本", archived: "历史资料" };

export function WorkspaceHome({ question, onQuestionChange, onSearch, searching, searchResult, searchResultRef, submittedQuery, resultCount, counts, projects, categoryNames, canReview, canViewLibraryTotals, reviewCount, onNavigate, onProjectSearch }: WorkspaceHomeProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const loading = counts === null;
  const metrics: HomeMetric[] = [
    { label: "可见资料项目", value: loading ? null : projects.length, note: "按当前账号权限展示", tone: "blue", icon: "项目管理" },
  ];
  if (canViewLibraryTotals) {
    metrics.push(
      { label: "登记文件", value: counts?.documents, note: "知识库已登记的文件", tone: "slate", icon: "合同档案库" },
      { label: "原件可用", value: counts?.source_available_documents, note: "当前可访问的原始文件", tone: "teal", icon: "shield" },
      { label: "当前版本文件", value: counts?.current_documents, note: counts?.current_documents === 0 ? "尚未发布当前版本" : "已发布的当前版本", tone: "amber", icon: "资料治理" },
    );
  } else {
    metrics.push({ label: "项目内可见文件", value: loading ? null : projects.reduce((sum, project) => sum + project.document_count, 0), note: "当前可见项目中的资料", tone: "teal", icon: "合同档案库" });
    if (canReview) metrics.push({ label: "待处理入库资料", value: loading ? null : reviewCount, note: "当前账号的入库处理队列", tone: "amber", icon: "入库审核" });
  }
  const tasks: { name: NavigationTab; title: string; note: string }[] = [
    { name: "AI资料检索", title: "AI资料检索", note: "查找项目经验，核对原文出处" },
    { name: "智能创作", title: "用智库写材料", note: "描述写作要求，引用已有资料" },
    canReview
      ? { name: "入库审核", title: "处理入库资料", note: loading ? "正在加载处理队列…" : reviewCount ? `${formatCount(reviewCount)} 份资料待处理` : "当前队列暂无待处理资料" }
      : { name: "资料上传", title: "上传工作资料", note: "上传文件，整理到授权分类" },
  ];

  function fillQuestion(value: string) {
    onQuestionChange(value);
    inputRef.current?.focus({ preventScroll: true });
  }

  return (
    <section className="homeWorkspace" aria-label="工作台概览">
      <section className="homeSearchHero" aria-labelledby="home-search-title">
        <div className="homeHeroHeader">
          <div className="homeHeroCopy"><p className="homeWelcome">资料检索 · 知识协作</p><h2 id="home-search-title">从资料中找到答案</h2><p className="homeHeroDescription">查找历史方案、培训材料与项目经验，让每一步工作都有依据。</p></div>
          <div className="homeSourceHint"><NavigationIcon name="shield" /><div><strong>保留来源与页码</strong><small>按账号权限查看资料</small></div></div>
        </div>
        <form className="homeSearchForm" onSubmit={(event) => { event.preventDefault(); if (!searching && question.trim()) void onSearch(); }} role="search">
          <div className="homeSearchField"><NavigationIcon name="AI资料检索" /><input ref={inputRef} type="search" aria-label="检索知识资料" value={question} onChange={(event) => onQuestionChange(event.target.value)} disabled={searching} placeholder="输入项目名称、资料关键词，或直接提问…" />{question && <button type="button" className="homeSearchClear" aria-label="清空检索内容" title="清空检索内容" disabled={searching} onClick={() => fillQuestion("")}><NavigationIcon name="close" /></button>}</div>
          <button type="submit" className="homeSearchSubmit" disabled={searching || !question.trim()}>{searching ? "检索中…" : "检索资料"}<NavigationIcon name="arrow-right" /></button>
        </form>
        <div className="homeExamples"><span>试试搜索</span>{["训练营方案", "赛事执行清单", "公司介绍"].map((example) => <button type="button" disabled={searching} key={example} onClick={() => fillQuestion(example)}>{example}</button>)}</div>
        <p className="homeSearchNote">支持项目名、关键词或自然语言提问。</p>
      </section>

      {(searching || searchResult) && <div className="homeSearchResult" ref={searchResultRef} role="region" aria-label="检索结果" aria-busy={searching} aria-live="polite"><header><h3>{searching ? "正在检索资料…" : "检索结果"}{!searching && resultCount !== null && <span>{formatCount(resultCount)} 份相关资料</span>}</h3>{!searching && <button type="button" className="homeResultLink" onClick={() => onNavigate("AI资料检索")}>查看完整结果<NavigationIcon name="arrow-right" /></button>}</header><p className="homeResultQuery">{submittedQuery}</p>{searching ? <p className="homeSearchPending" role="status">正在查找当前账号有权限查看的资料…</p> : <div className="homeResultBody">{searchResult}</div>}</div>}

      <section className="homeMetricGrid" data-count={metrics.length} aria-label="资料概览">
        {metrics.map((metric) => {
          const formatted = formatCount(metric.value);
          return <article className="homeMetricCard" data-tone={metric.tone} data-long={formatted.length > 9} key={metric.label}><div className="homeMetricHeading"><span>{metric.label}</span><NavigationIcon name={metric.icon} /></div><strong className="homeMetricValue">{formatted}</strong><small className="homeMetricNote">{loading ? "正在加载统计…" : formatted === "—" ? "统计暂未提供" : metric.note}</small></article>;
        })}
      </section>

      <section className="homeContentGrid">
        <section className="homeRecentPanel" aria-labelledby="home-projects-title">
          <header className="homePanelHeader"><div><h2 id="home-projects-title">项目资料</h2><p>按资料年份浏览，展示当前账号可见项目。</p></div><button type="button" onClick={() => onNavigate("AI资料检索")}>查看全部资料<NavigationIcon name="arrow-right" /></button></header>
          {loading ? <div className="homeProjectLoading" role="status">正在加载项目资料…</div> : !projects.length ? <div className="homeEmptyState"><NavigationIcon name="项目管理" /><h3>还没有可显示的项目资料</h3><p>在当前账号权限范围内的项目资料会显示在这里。</p><button type="button" onClick={() => onNavigate("资料上传")}>去上传资料<NavigationIcon name="arrow-right" /></button></div> : <ul className="homeProjectList">
            {projects.slice(0, 5).map((project) => <li className="homeProjectRow" key={project.id}><button type="button" className="homeProjectButton" aria-label={`检索项目资料：${project.name}`} disabled={searching} onClick={() => void onProjectSearch(project.name)}><span className="homeProjectIcon"><NavigationIcon name="项目管理" /></span><span className="homeProjectIdentity"><strong className="homeProjectName">{project.name}</strong><span className="homeProjectDescription">{project.client || "客户未填写"} · {project.year ? `${project.year} 年` : "年份未填写"}</span><span className="homeProjectBadges"><span className="homeCategoryBadge">{categoryNames[project.domain] || project.domain || "未分类"}</span><span className="homeKnowledgeBadge" data-status={project.knowledge_status}>{knowledgeLabels[project.knowledge_status] || "历史资料"}</span>{project.closing_report_reminder && <span className="homeClosingBadge">缺结案报告</span>}</span></span><span className="homeProjectMeta"><strong>{formatCount(project.document_count)} 份资料</strong><span>检索资料<NavigationIcon name="arrow-right" /></span></span></button></li>)}
          </ul>}
        </section>
        <aside className="homeSideColumn" aria-label="常用操作与资料说明">
          <section className="homeTasksPanel" aria-labelledby="home-tasks-title"><header className="homePanelHeader"><div><h2 id="home-tasks-title">常用操作</h2><p>从查找资料到整理成果</p></div></header><div className="homeTaskList">{tasks.map((task) => <button type="button" className="homeTaskButton" key={task.name} onClick={() => onNavigate(task.name)}><span className="homeTaskIcon"><NavigationIcon name={task.name} /></span><span className="homeTaskCopy"><strong>{task.title}</strong><small>{task.note}</small></span><NavigationIcon name="arrow-right" /></button>)}</div></section>
          <section className="homeSourceCard"><NavigationIcon name="shield" /><h3>结果可追溯</h3><p>答案保留资料来源与页码。打开原文、核对内容后，再用于实际工作。</p></section>
        </aside>
      </section>
    </section>
  );
}
