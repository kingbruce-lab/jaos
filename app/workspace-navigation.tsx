"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";

export type NavigationTab = "工作台" | "财务分析" | "项目管理" | "资料上传" | "合同档案库" | "AI资料检索" | "智能创作" | "入库审核" | "资料治理" | "知识进化" | "系统状态" | "账号管理";

export type WorkspaceNavigationProps = {
  active: NavigationTab;
  visibleTabs: { name: NavigationTab; icon?: string }[];
  financeEntities: { id: string; display_name: string; business_name: string }[];
  selectedFinanceEntityId: string;
  reviewCount: number;
  outboundEnabled: boolean;
  user: { name: string; roleLabel: string; levelLabel: string };
  onNavigate: (tab: NavigationTab) => void;
  onEntitySelect: (entityId: string) => void;
  onPasswordChange: () => void;
  onLogout: () => void | Promise<void>;
};

const navigationGroups: { key: string; title: string; items: NavigationTab[] }[] = [
  { key: "workspace", title: "工作空间", items: ["工作台", "项目管理", "财务分析", "合同档案库"] },
  { key: "knowledge", title: "知识协作", items: ["AI资料检索", "智能创作", "资料上传"] },
  { key: "management", title: "管理与设置", items: ["入库审核", "资料治理", "知识进化", "系统状态", "账号管理"] },
];

const mobilePrimaryTabNames: NavigationTab[] = ["工作台", "AI资料检索", "智能创作", "资料上传"];
const SIDEBAR_MODE_KEY = "jaos-navigation-mode";
type SidebarMode = "auto" | "compact" | "expanded";
type IconName = NavigationTab | "collapse" | "expand" | "chevron" | "arrow-right" | "password" | "logout" | "more" | "close" | "shield";

function storedSidebarMode(): SidebarMode {
  try {
    const stored = localStorage.getItem(SIDEBAR_MODE_KEY);
    if (stored === "compact" || stored === "expanded") return stored;
  } catch { /* Browser storage is optional. */ }
  return "auto";
}

function subscribeSidebarMode(onChange: () => void) {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
}

function subscribeNarrowSidebar(onChange: () => void) {
  const query = window.matchMedia("(max-width: 1100px)");
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

const isNarrowSidebar = () => window.matchMedia("(max-width: 1100px)").matches;
const serverSidebarMode = (): SidebarMode => "auto";
const serverNarrowSidebar = () => false;

export function NavigationIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    工作台: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" /><path d="M9 21v-8h6v8" /></>,
    财务分析: <><path d="M4 20V11m5 9v-6m5 6V9m5 11V4M3 7l6 3 10-7" /></>,
    项目管理: <><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" /><path d="M8 12h8m-8 4h5" /></>,
    资料上传: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5" /></>,
    合同档案库: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Zm0 0v6h6M8 13h8m-8 4h5" /></>,
    AI资料检索: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5M8 10.5h5m-2.5-2.5v5" /></>,
    智能创作: <><path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14ZM4 20h16" /></>,
    入库审核: <><path d="M9 4H6a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-3" /><rect x="9" y="2" width="6" height="4" rx="1" /><path d="m8 13 3 3 5-6" /></>,
    资料治理: <><path d="m3 7 9-4 9 4-9 4Zm0 5 9 4 9-4M3 17l9 4 9-4" /></>,
    知识进化: <><path d="M5 19 19 5M5 11V5h6m2 14h6v-6" /><path d="M5 5l14 14" /></>,
    系统状态: <><rect x="3" y="4" width="18" height="14" rx="2" /><path d="M7 22h10m-5-4v4M6 11h3l2-4 3 8 2-4h2" /></>,
    账号管理: <><circle cx="9" cy="7" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6m3 11v-3a6 6 0 0 0-3-5" /></>,
    collapse: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16m7-12-4 4 4 4" /></>,
    expand: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16m4-12 4 4-4 4" /></>,
    chevron: <path d="m8 10 4 4 4-4" />,
    "arrow-right": <path d="M4 12h16m-6-6 6 6-6 6" />,
    password: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" /></>,
    logout: <><path d="M9 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4m6-12 4 4-4 4m-7-4h13" /></>,
    more: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z" /><path d="m8 12 3 3 5-6" /></>,
  };
  return <svg className="workspaceNavIcon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{paths[name]}</svg>;
}

function ReviewBadge({ count }: { count: number }) {
  return count > 0 ? <b className="workspaceNavCount" aria-label={`待审核 ${count} 项`} title={`待审核 ${count} 项`}>{count > 99 ? "99+" : count}</b> : null;
}

export function WorkspaceSidebar({ active, visibleTabs, financeEntities, selectedFinanceEntityId, reviewCount, outboundEnabled, user, onNavigate, onEntitySelect, onPasswordChange, onLogout }: WorkspaceNavigationProps) {
  const storedMode = useSyncExternalStore(subscribeSidebarMode, storedSidebarMode, serverSidebarMode);
  const [modeOverride, setMode] = useState<SidebarMode | null>(null);
  const mode = modeOverride || storedMode;
  const narrow = useSyncExternalStore(subscribeNarrowSidebar, isNarrowSidebar, serverNarrowSidebar);
  const [financeDisclosure, setFinanceDisclosure] = useState<{ page: NavigationTab; open: boolean } | null>(null);
  const financeExpanded = financeDisclosure?.page === active ? financeDisclosure.open : active === "财务分析";
  const collapsed = mode === "compact" || (mode === "auto" && narrow);

  function toggleSidebar() {
    const next = collapsed ? "expanded" : "compact";
    setMode(next);
    try { localStorage.setItem(SIDEBAR_MODE_KEY, next); } catch { /* Optional preference. */ }
  }

  return (
    <aside className="sidebar workspaceSidebar" aria-label="桌面导航栏" data-mode={mode} data-collapsed={collapsed}>
      <header className="workspaceSidebarHeader">
        <div className="workspaceBrand" aria-label="京奥AI智能运营系统 · JAOS">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="workspaceBrandMark" src="/jingao-mark-transparent.png" alt="京奥电竞" width={48} height={48} />
          <div className="workspaceBrandCopy"><strong>京奥AI</strong><small>智能运营系统</small><span>JAOS</span></div>
        </div>
        <button type="button" className="workspaceCollapseButton" aria-label={collapsed ? "展开导航" : "收起导航"} title={collapsed ? "展开导航" : "收起导航"} aria-expanded={!collapsed} aria-controls="workspace-main-navigation" onClick={toggleSidebar}><NavigationIcon name={collapsed ? "expand" : "collapse"} /></button>
      </header>

      <nav className="workspaceNav" id="workspace-main-navigation" aria-label="主导航">
        {navigationGroups.map((group) => {
          const items = group.items.filter((name) => visibleTabs.some((tab) => tab.name === name));
          return items.length ? (
            <section className="workspaceNavGroup" aria-labelledby={`workspace-group-${group.key}`} key={group.key}>
              <h2 className="workspaceNavGroupTitle" id={`workspace-group-${group.key}`}>{group.title}</h2>
              <div className="workspaceNavGroupItems">
                {items.map((name) => (
                  <div className="workspaceNavEntry" key={name}>
                    <div className="workspaceNavRow" data-active={active === name}>
                      <button type="button" className="workspaceNavButton" aria-label={name} aria-current={active === name ? "page" : undefined} title={collapsed ? name : undefined} onClick={() => { onNavigate(name); setFinanceDisclosure({ page: name, open: name === "财务分析" }); }}>
                        <NavigationIcon name={name} /><span className="workspaceNavLabel">{name}</span>
                        {name === "入库审核" && <ReviewBadge count={reviewCount} />}
                      </button>
                      {name === "财务分析" && financeEntities.length > 0 && <button type="button" className="workspaceSubnavToggle" aria-label={financeExpanded ? "收起财务账套" : "展开财务账套"} aria-expanded={financeExpanded} aria-controls="workspace-finance-entities" onClick={() => setFinanceDisclosure({ page: active, open: !financeExpanded })}><NavigationIcon name="chevron" /></button>}
                    </div>
                    {name === "财务分析" && financeEntities.length > 0 && (
                      <div id="workspace-finance-entities" className="workspaceFinanceSubnav" aria-label="财务公司账套" hidden={!financeExpanded || collapsed}>
                        {financeEntities.map((entity) => (
                          <button type="button" className="workspaceEntityButton" key={entity.id} aria-label={`打开${entity.display_name}账套`} aria-current={active === "财务分析" && selectedFinanceEntityId === entity.id ? "page" : undefined} onClick={() => onEntitySelect(entity.id)}>
                            <span className="workspaceEntityDot" aria-hidden="true" /><span className="workspaceEntityCopy"><strong>{entity.display_name}</strong><small>{entity.business_name}</small></span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          ) : null;
        })}
      </nav>

      <footer className="workspaceSidebarFooter">
        <div className="workspaceAccessStatus" data-outbound={outboundEnabled} title={outboundEnabled ? "已启用出网" : "当前资料不出网"}>
          <NavigationIcon name="shield" /><div><strong>资料访问</strong><small>{outboundEnabled ? "已启用出网" : "当前资料不出网"}</small></div><i className="workspaceAccessDot" aria-hidden="true" />
        </div>
        <div className="workspaceAccount">
          <div className="workspaceAccountIdentity"><span className="workspaceAvatar" aria-hidden="true">{user.name.slice(0, 1)}</span><div className="workspaceAccountCopy"><strong>{user.name}</strong><small>{user.roleLabel}</small><small>{user.levelLabel}</small></div></div>
          <div className="workspaceAccountActions">
            <button type="button" aria-label="修改密码" title="修改密码" onClick={onPasswordChange}><NavigationIcon name="password" /><span>修改密码</span></button>
            <button type="button" aria-label="退出登录" title="退出登录" onClick={() => void onLogout()}><NavigationIcon name="logout" /><span>退出登录</span></button>
          </div>
        </div>
      </footer>
    </aside>
  );
}

export function WorkspaceMobileNavigation({ active, visibleTabs, financeEntities, selectedFinanceEntityId, reviewCount, outboundEnabled, user, onNavigate, onEntitySelect, onPasswordChange, onLogout }: WorkspaceNavigationProps) {
  const [open, setOpen] = useState(false);
  const sheetRef = useRef<HTMLElement | null>(null);
  const moreButtonRef = useRef<HTMLButtonElement | null>(null);
  const primaryTabs = mobilePrimaryTabNames.filter((name) => visibleTabs.some((tab) => tab.name === name));
  const moreTabs = visibleTabs.filter((tab) => !mobilePrimaryTabNames.includes(tab.name));
  const moreActive = moreTabs.some((tab) => tab.name === active);

  useEffect(() => {
    if (!open) return;
    const sheet = sheetRef.current;
    if (!sheet) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : moreButtonRef.current;
    const previousOverflow = document.body.style.overflow;
    const shell = sheet.closest(".workspaceShell");
    const background = Array.from(shell?.children || []).filter((element): element is HTMLElement => element instanceof HTMLElement && !element.contains(sheet));
    const previousInert = background.map((element) => element.inert);
    background.forEach((element) => { element.inert = true; });
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(sheet.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')).filter((element) => element.getClientRects().length > 0);
    focusable()[0]?.focus({ preventScroll: true });
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setOpen(false); }
      if (event.key !== "Tab") return;
      const controls = focusable();
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    const desktop = window.matchMedia("(min-width: 761px)");
    const closeOnDesktop = () => { if (desktop.matches) setOpen(false); };
    window.addEventListener("keydown", handleKeyDown);
    desktop.addEventListener("change", closeOnDesktop);
    return () => {
      document.body.style.overflow = previousOverflow;
      background.forEach((element, index) => { element.inert = previousInert[index]; });
      window.removeEventListener("keydown", handleKeyDown);
      desktop.removeEventListener("change", closeOnDesktop);
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, [open]);

  function navigate(name: NavigationTab) { setOpen(false); onNavigate(name); }

  return (
    <>
      <nav className="mobileTabbar workspaceMobileTabbar" aria-label="手机端主导航">
        {primaryTabs.map((name) => <button type="button" key={name} className={active === name ? "active" : ""} aria-current={active === name ? "page" : undefined} onClick={() => navigate(name)}><NavigationIcon name={name} /><span>{name === "AI资料检索" ? "资料检索" : name}</span></button>)}
        <button type="button" ref={moreButtonRef} className={open || moreActive ? "active" : ""} aria-expanded={open} aria-controls="mobile-more-sheet" onClick={() => setOpen(true)}><NavigationIcon name="more" /><span>更多</span></button>
      </nav>
      {open && (
        <div className="mobileMenuBackdrop workspaceMobileBackdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
          <section className="mobileMenuSheet workspaceMobileSheet" id="mobile-more-sheet" ref={sheetRef} role="dialog" aria-modal="true" aria-labelledby="mobile-more-title">
            <div className="mobileMenuHandle" aria-hidden="true" />
            <header className="workspaceMobileHeader"><div><p>京奥AI · JAOS</p><h2 id="mobile-more-title">更多功能</h2></div><button type="button" aria-label="关闭更多功能" onClick={() => setOpen(false)}><NavigationIcon name="close" /></button></header>
            <div className="workspaceMobileUser"><span className="workspaceAvatar" aria-hidden="true">{user.name.slice(0, 1)}</span><div><strong>{user.name}</strong><small>{user.roleLabel} · {user.levelLabel}</small><small>{outboundEnabled ? "已启用出网" : "当前资料不出网"}</small></div></div>
            <nav className="workspaceMobileModules" aria-label="更多功能列表">
              {navigationGroups.map((group) => {
                const items = group.items.filter((name) => moreTabs.some((tab) => tab.name === name));
                return items.length ? <section className="workspaceMobileGroup" key={group.key} aria-labelledby={`workspace-mobile-group-${group.key}`}><h3 id={`workspace-mobile-group-${group.key}`}>{group.title}</h3><div className="workspaceMobileGroupItems">
                  {items.map((name) => <div className="workspaceMobileEntry" key={name}><button type="button" className="workspaceMobileModule" aria-current={active === name ? "page" : undefined} onClick={() => navigate(name)}><NavigationIcon name={name} /><span>{name}</span>{name === "入库审核" && <ReviewBadge count={reviewCount} />}</button>
                    {name === "财务分析" && financeEntities.length > 0 && <div className="workspaceMobileEntities" aria-label="财务公司账套">{financeEntities.map((entity) => <button type="button" key={entity.id} aria-label={`打开${entity.display_name}账套`} aria-current={active === "财务分析" && selectedFinanceEntityId === entity.id ? "page" : undefined} onClick={() => { setOpen(false); onEntitySelect(entity.id); }}><span className="workspaceEntityDot" aria-hidden="true" /><span><strong>{entity.display_name}</strong><small>{entity.business_name}</small></span></button>)}</div>}
                  </div>)}
                </div></section> : null;
              })}
            </nav>
            <div className="workspaceMobileActions"><button type="button" aria-label="修改密码" onClick={() => { setOpen(false); onPasswordChange(); }}><NavigationIcon name="password" />修改密码</button><button type="button" aria-label="退出登录" onClick={() => { setOpen(false); void onLogout(); }}><NavigationIcon name="logout" />退出登录</button></div>
          </section>
        </div>
      )}
    </>
  );
}
