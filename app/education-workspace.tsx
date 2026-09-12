"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import "./education.css";
import { EducationCostClassification, EducationEnrollment } from "./education-enrollment";
import { EducationCohortDelete } from "./education-cohort-delete";
import { EducationLedgerOverview } from "./education-ledger";
import { EducationOperations } from "./education-operations";

type Api = <T>(path: string, options?: RequestInit, token?: string) => Promise<T>;
type Summary = { cohort_count: number; student_count: number; expected_income: string; income: string; expense: string; net: string };
type Cohort = { id: string; name: string; start_date: string; end_date: string; course_period?: string; enrollment_count?: number; effective_student_count?: number; student_count: number; unit_price: string; notes: string; version: number; owner_name: string; expected_income: string; income: string; expense: string; net: string };
type Entry = { id: string; direction: "income" | "expense"; amount: string; occurred_on: string; purpose: string; version: number; category?: string; detail?: string; staff_id?: string | null };
type Registry = { items: Cohort[]; summary: Summary; enrollment_summary?: { receivable: string; received: string; arrears: string }; has_more: boolean; can_edit: boolean; can_delete?: boolean; scope: string };
const money = (value: string) => Number(value).toLocaleString("zh-CN", { style: "currency", currency: "CNY" });
const today = () => new Date().toLocaleDateString("sv-SE");

function CohortFields({ cohort }: { cohort?: Cohort }) {
  return <>
    <label>班期名称<input name="education_cohort_name" autoComplete="off" required maxLength={120} placeholder="自行填写班期名称" defaultValue={cohort?.name} /></label>
    <label>开班日期<input name="start_date" type="date" required min="2000-01-01" max="2100-12-31" defaultValue={cohort?.start_date || today()} /></label>
    <label>班期课程周期<select name="course_period" defaultValue={cohort?.course_period || "1_month"}><option value="8_days">八天七晚</option><option value="1_month">一个月</option><option value="3_months">三个月</option></select></label>
    <label>生源人数<input name="student_count" type="number" required min="0" max="100000" step="1" defaultValue={cohort?.student_count ?? 0} /></label>
    <label>客单价（元/人/期）<input name="unit_price" type="number" required min="0" max="9999999999.99" step="0.01" defaultValue={cohort?.unit_price || "0"} /></label>
    <label className="educationWide">备注<textarea name="notes" maxLength={2000} defaultValue={cohort?.notes} placeholder="可记录招生进展、托管安排等，无需填写学员敏感个人信息" /></label>
  </>;
}

function EntryFields({ entry }: { entry?: Entry }) {
  return <>
    <label>收支方向<select name="direction" defaultValue={entry?.direction || "income"}><option value="income">收入</option><option value="expense">支出</option></select></label>
    <label>金额（元）<input name="amount" type="number" min="0.01" max="9999999999.99" step="0.01" required defaultValue={entry?.amount} /></label>
    <label>发生日期<input name="occurred_on" type="date" required defaultValue={entry?.occurred_on || today()} /></label>
    <label className="educationWide">收支用途<input name="purpose" required maxLength={500} defaultValue={entry?.purpose} placeholder="例如：本期学费、住宿、餐饮、教练课酬" /></label>
  </>;
}

export function EducationWorkspace({ api, token, initialModule = "ledger" }: { api: Api; token: string; initialModule?: "ledger" | "cohorts" }) {
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<(Cohort & { entries: Entry[] }) | null>(null);
  const [editing, setEditing] = useState<Entry | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [formKey, setFormKey] = useState(0);
  const [module, setModule] = useState<"ledger" | "cohorts">(initialModule);
  const createId = useRef<string | null>(null);
  const entryId = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api<Registry>("v1/pm/education/cohorts", { signal: controller.signal }, token)
      .then(setRegistry).catch((cause) => { if (!controller.signal.aborted) setError(String(cause.message || cause)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, token, revision]);

  useEffect(() => {
    setDetail(null);
    setEditing(null);
    entryId.current = null;
    if (!selectedId) return;
    const controller = new AbortController();
    api<Cohort & { entries: Entry[] }>(`v1/pm/education/cohorts/${selectedId}`, { signal: controller.signal }, token)
      .then(setDetail).catch((cause) => { if (!controller.signal.aborted) setError(String(cause.message || cause)); });
    return () => controller.abort();
  }, [api, token, selectedId, revision]);

  async function submit(event: FormEvent<HTMLFormElement>, action: "create" | "cohort" | "entry" | "correct") {
    event.preventDefault();
    if (busy || !registry?.can_edit) return;
    const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    let path = "v1/pm/education/cohorts";
    const isCohort = action === "create" || action === "cohort";
    if (isCohort) { values.name = values.education_cohort_name; delete values.education_cohort_name; }
    const body: Record<string, unknown> = isCohort
      ? { ...values, student_count: Number(values.student_count) }
      : values;
    if (!isCohort) body.staff_id = values.staff_id || null;
    if (action === "create") {
      createId.current ||= crypto.randomUUID();
      body.request_id = createId.current;
    } else if (action === "cohort") {
      if (!detail) return;
      path += `/${detail.id}`;
      body.version = detail.version;
    } else {
      if (!detail) return;
      path += `/${detail.id}/entries`;
      if (action === "correct") {
        if (!editing) return;
        path += `/${editing.id}`;
        body.version = editing.version;
      } else {
        entryId.current ||= crypto.randomUUID();
        body.request_id = entryId.current;
      }
    }
    setBusy(action); setError(""); setMessage("");
    try {
      const result = await api<{ id: string }>(path, {
        method: action === "cohort" || action === "correct" ? "PATCH" : "POST",
        body: JSON.stringify(body), signal: AbortSignal.timeout(20000),
      }, token);
      if (action === "create") { createId.current = null; setSelectedId(result.id); }
      entryId.current = null;
      setEditing(null); setFormKey((key) => key + 1); setRevision((value) => value + 1);
      setMessage("已保存，班期及累计统计已更新。");
    } catch (cause) {
      setError(cause instanceof Error ? `${cause.message}。若提示已更新或请求超时，请先刷新核对记录。` : "保存失败，请重试");
    } finally { setBusy(""); }
  }

  async function loadMore() {
    if (!registry || busy) return;
    setBusy("more"); setError("");
    try {
      const next = await api<Registry>(`v1/pm/education/cohorts?offset=${registry.items.length}`, {}, token);
      setRegistry({ ...next, items: [...registry.items, ...next.items] });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "加载失败"); }
    finally { setBusy(""); }
  }

  return <section className="educationWorkspace">
    <section className="panel educationHeader">
      <div><p className="eyebrow">XINGYAO · EDUCATION</p><h2>星曜电竞 · 托管式教培</h2>
        <p>按课程周期登记学员、收费与成本，持续跟踪成长。{registry?.scope === "mine" ? "当前仅显示自己登记的班期。" : "管理及财务可查看全部班期。"}</p></div>
      <button type="button" className="secondaryButton" disabled={!!busy || loading} onClick={() => { setError(""); setRevision((value) => value + 1); }}>刷新数据</button>
    </section>
    {error && <div role="alert" className="educationError">{error}</div>}
    {message && <div role="status" className="noticeBar">{message}</div>}
    {loading && <p role="status">正在加载教培数据…</p>}
    {registry && <>
      <div className="educationModuleTabs" aria-label="星曜教培模块">
        <button type="button" className={module === "ledger" ? "active" : ""} onClick={() => setModule("ledger")}>综合台账</button>
        <button type="button" className={module === "cohorts" ? "active" : ""} onClick={() => setModule("cohorts")}>班期管理</button>
      </div>
      {module === "ledger" && <EducationLedgerOverview api={api} token={token} cohorts={registry.items} onOpenCohort={(id) => { setSelectedId(id); setModule("cohorts"); }} />}
      {module === "cohorts" && <>
      <section className="educationMetrics" aria-label="教培累计统计">
        <article><span>累计班期</span><strong>{registry.summary.cohort_count} 期</strong></article>
        <article><span>累计生源（人次）</span><strong>{registry.summary.student_count}</strong></article>
        <article><span>预计收入 · 报名应收优先</span><strong>{money(registry.summary.expected_income)}</strong></article>
        <article><span>累计实际收入</span><strong>{money(registry.summary.income)}</strong></article>
        <article><span>累计实际支出</span><strong>{money(registry.summary.expense)}</strong></article>
        <article><span>累计收支结余</span><strong>{money(registry.summary.net)}</strong></article>
      </section>
      {registry.enrollment_summary && <section className="educationMetrics"><article><span>学员应收合计</span><strong>{money(registry.enrollment_summary.receivable)}</strong></article><article><span>学员已收金额</span><strong>{money(registry.enrollment_summary.received)}</strong></article><article><span>学员欠费合计</span><strong>{money(registry.enrollment_summary.arrears)}</strong></article></section>}
      <p className="educationHint">已登记学员的班期按报名记录统计人数及应收；尚未逐位登记的班期沿用手工人数×客单价。实际收支＝学员已收 / 成本＋班期公共收支，请勿重复登记。同一学员参加多期计多人次，不自动生成银行流水。</p>
      {registry.can_edit && <details className="panel" key={`create-${formKey}`}>
        <summary>＋ 新增招生班期</summary>
        <form className="educationForm" onSubmit={(event) => void submit(event, "create")}>
          <CohortFields /><p className="educationWide educationHint">结束日期按首尾都计入自动计算：八天七晚8天、一个月29天、三个月87天；授课日与自主练习日按实际课表安排。</p>
          <button className="primaryButton" disabled={!!busy}>{busy === "create" ? "保存中…" : "创建班期"}</button>
        </form>
      </details>}
      <section className="panel">
        <h3>{registry.scope === "mine" ? "我的教培班期" : "全部教培班期"}（{registry.summary.cohort_count}）</h3>
        {registry.items.length === 0 && <p>暂无班期。教培员工可从“新增招生班期”开始登记。</p>}
        <div className="educationCohortList">{registry.items.map((cohort) => <button type="button" className={selectedId === cohort.id ? "active" : ""} key={cohort.id}
          disabled={!!busy} onClick={() => { setSelectedId(cohort.id); setError(""); setMessage(""); }}>
          <strong>{cohort.name}</strong><span>{cohort.start_date} 至 {cohort.end_date} · 登记人：{cohort.owner_name}</span>
          <span>{cohort.effective_student_count ?? cohort.student_count} 人 · {cohort.enrollment_count ? "已按报名记录统计" : `预估客单价 ${money(cohort.unit_price)}`}</span>
          <span>收入 {money(cohort.income)} · 支出 {money(cohort.expense)} · 结余 {money(cohort.net)}</span>
        </button>)}</div>
        {registry.has_more && <button type="button" className="secondaryButton" disabled={!!busy} onClick={() => void loadMore()}>加载更多班期</button>}
      </section>
      {selectedId && !detail && <p role="status">正在加载班期详情…</p>}
      {detail && <section className="panel educationDetail">
        <h3>{detail.name}</h3><p>{detail.start_date} 至 {detail.end_date} · 登记人：{detail.owner_name}</p>
        {registry.can_delete && <EducationCohortDelete key={`${detail.id}-${detail.version}`} api={api} token={token} cohort={detail} onDeleted={() => { setSelectedId(""); setDetail(null); setRevision((value) => value + 1); setMessage("班期已删除，已从日常页面及教培汇总移除；历史资料保留供追溯。"); }} />}
        <div className="educationMetrics">
          <article><span>本期人数</span><strong>{detail.effective_student_count ?? detail.student_count} 人</strong></article>
          <article><span>预计收入</span><strong>{money(detail.expected_income)}</strong></article>
          <article><span>本期实际收入</span><strong>{money(detail.income)}</strong></article>
          <article><span>本期实际支出</span><strong>{money(detail.expense)}</strong></article>
          <article><span>本期收支结余</span><strong>{money(detail.net)}</strong></article>
        </div>
        {detail.notes && <p className="educationNotes">{detail.notes}</p>}
        <EducationEnrollment key={`${detail.id}-${revision}`} api={api} token={token} cohortId={detail.id} start={detail.start_date} period={detail.course_period || "1_month"} canEdit={registry.can_edit} onSaved={() => { setMessage("已保存，报名与班期汇总已更新。"); setRevision((value) => value + 1); }} />
        <EducationOperations key={`operations-${detail.id}`} api={api} token={token} cohortId={detail.id} canEdit={registry.can_edit} cohorts={registry.items.map((item) => ({ id: item.id, name: item.name }))} />
        {registry.can_edit && <>
          <details key={`${detail.id}-${detail.version}`}><summary>编辑班期、招生人数和客单价</summary>
            <form className="educationForm" onSubmit={(event) => void submit(event, "cohort")}><CohortFields cohort={detail} /><button className="primaryButton" disabled={!!busy}>保存班期</button></form>
          </details>
          <h4>{editing ? "修正收支记录" : "追加收入 / 支出"}</h4>
          <p className="educationHint">此处登记班期公共收支（如公共教师成本）。学员费用已在报名表自动计入，请勿重复添加。</p>
          <form className="educationForm" key={`${detail.id}-${editing?.id || "new"}-${formKey}`} onSubmit={(event) => void submit(event, editing ? "correct" : "entry")}>
            <EducationCostClassification key={`${revision}-${editing?.id || "new"}`} api={api} token={token} cohortId={detail.id} entry={editing || undefined} />
            <EntryFields entry={editing || undefined} /><button className="primaryButton" disabled={!!busy}>{editing ? "保存修正" : "追加收支"}</button>
            {editing && <button type="button" disabled={!!busy} onClick={() => setEditing(null)}>取消修正</button>}
          </form>
        </>}
        <h4>本期公共收支明细（{detail.entries.length}）</h4>
        <p className="educationHint">修正会保留操作记录，不会重复累计。</p>
        {!detail.entries.length && <p>尚未登记收支。</p>}
        <div className="educationEntries">{detail.entries.map((entry) => <article key={entry.id}>
          <div><strong>{entry.direction === "income" ? "收入" : "支出"} {money(entry.amount)}</strong><span>{entry.occurred_on} · {entry.category || "其他"} / {entry.detail || "其他"} · {entry.purpose}</span></div>
          {registry.can_edit && <button type="button" disabled={!!busy} onClick={() => setEditing(entry)}>修正</button>}
        </article>)}</div>
      </section>}
      </>}
    </>}
  </section>;
}

export function AccountRoleFields({ initialRole = "business", initialCeiling = "L1" }: { initialRole?: string; initialCeiling?: string }) {
  const [role, setRole] = useState(initialRole);
  const [ceiling, setCeiling] = useState(initialCeiling);
  const levels = ["L1", "L2", "L3", "L4", "L5"];
  const labels = ["公司公共资料", "业务普通资料", "业务敏感资料", "核心保密资料", "公司最高机密"];
  return <>
    <label>角色<select name="role" value={role} onChange={(event) => { setRole(event.target.value); if (event.target.value === "education") setCeiling("L1"); }}>
      <option value="administrative">行政</option><option value="personnel">人事</option><option value="business">业务</option>
      <option value="education">教培</option><option value="finance">财务</option><option value="management">管理</option>
    </select></label>
    <label>可见密级<select name="confidentiality_ceiling" value={role === "education" ? "L1" : ceiling} onChange={(event) => setCeiling(event.target.value)}>
      {levels.map((level, index) => <option value={level} key={level} disabled={role === "education" && level !== "L1"}>{level} · {labels[index]}</option>)}
    </select>{role === "education" && <small>固定 L1，可使用教培项目模块</small>}</label>
  </>;
}
