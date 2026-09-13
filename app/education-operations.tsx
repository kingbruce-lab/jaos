"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

type Api = <T>(path: string, options?: RequestInit, token?: string) => Promise<T>;
type Day = { id: string; calendar_date: string; day_number: number; day_type: "teaching" | "practice" | "rest"; title: string; notes: string; version: number };
type CostAllocation = { id: string; cohort_id: string; cohort_name?: string; student_id: string | null; student_name: string | null; allocation_month: string; amount: string; note?: string };
type Cost = { id: string; occurred_on: string; category: string; detail: string; amount: string; allocated_amount: string; vendor: string; document_no: string; source_ref: string; note: string; allocations: CostAllocation[]; version: number };
type CostDetail = Cost & { allocation_mode: "cohort" | "equal_students" | "custom"; allocation_month: string | null; can_edit: boolean; has_hidden_allocations: boolean };
type DailyLog = { id: string; log_date: string; staff_id: string; staff_name: string; staff_role: string; log_type: string; summary: string; follow_up: string; student_ids: string[]; version: number };
type Operations = { schedule: { generated: boolean; days: Day[]; summary: { teaching: number; practice: number; rest: number } }; costs: { items: Cost[]; source_total: string; allocated_to_cohort: string }; logs: DailyLog[]; missing_log_days: string[]; can_view_logs: boolean; can_edit: boolean };
type Staff = { id: string; name: string; role: string; active: boolean };
type Student = { id: string; name: string; student_no?: string | null };
type CohortOption = { id: string; name: string };
type CustomAllocation = { cohort_id: string; allocation_month: string; amount: string; note: string };

const costDetails: Record<string, string[]> = {
  "住宿费": ["一人间", "两人间", "其他"],
  "饭费": ["早餐", "午餐", "晚餐", "餐费套餐", "其他"],
  "零食费": ["零食", "饮料", "水果", "其他"],
  "活动经费": ["团建活动", "外出参观", "交通费", "场地费", "活动物料", "比赛报名费", "奖品", "其他"],
  "人员成本": ["王者荣耀教师", "英雄联盟教师", "三角洲行动教师", "无畏契约教师", "CS2教师", "班主任", "生活老师", "状态恢复师", "助教", "其他教师"],
  "推荐渠道提成费": ["推荐人提成", "渠道提成", "其他"],
  "其他": ["其他"],
};
const money = (value: string) => Number(value).toLocaleString("zh-CN", { style: "currency", currency: "CNY" });
const today = () => new Date().toLocaleDateString("sv-SE");

export function EducationOperations({ api, token, cohortId, canEdit, cohorts }: { api: Api; token: string; cohortId: string; canEdit: boolean; cohorts: CohortOption[] }) {
  const [data, setData] = useState<Operations | null>(null);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [category, setCategory] = useState("住宿费");
  const [allocationMode, setAllocationMode] = useState<"cohort" | "equal_students" | "custom">("cohort");
  const [customAllocations, setCustomAllocations] = useState<CustomAllocation[]>([{ cohort_id: cohortId, allocation_month: today().slice(0, 7), amount: "", note: "" }]);
  const [logTypeFilter, setLogTypeFilter] = useState("");
  const [staffFilter, setStaffFilter] = useState("");
  const [editingCost, setEditingCost] = useState<CostDetail | null>(null);
  const [editCategory, setEditCategory] = useState("住宿费");
  const [editAllocationMode, setEditAllocationMode] = useState<"cohort" | "equal_students" | "custom">("cohort");
  const [editAllocations, setEditAllocations] = useState<CustomAllocation[]>([]);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const logId = useRef<string | null>(null);
  const costId = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api<Operations>(`v1/pm/education/cohorts/${cohortId}/operations`, { signal: controller.signal }, token),
      api<{ items: Staff[] }>(`v1/pm/education/cohorts/${cohortId}/staff`, { signal: controller.signal }, token),
      api<{ items: Student[] }>(`v1/pm/education/cohorts/${cohortId}/students?limit=100`, { signal: controller.signal }, token),
    ]).then(([operations, staffRegistry, studentRegistry]) => {
      setData(operations); setStaff(staffRegistry.items); setStudents(studentRegistry.items);
    }).catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "运营台账加载失败"); });
    return () => controller.abort();
  }, [api, cohortId, revision, token]);

  async function generateSchedule() {
    if (busy || !canEdit) return;
    setBusy("schedule"); setError(""); setMessage("");
    try {
      const result = await api<{ created: number; total_days: number }>(`v1/pm/education/cohorts/${cohortId}/schedule/generate`, { method: "POST" }, token);
      setMessage(result.created ? `已按6天授课＋1天自主练习生成 ${result.total_days} 天课表。` : "课表已存在，未覆盖人工调整。");
      setRevision((value) => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "生成课表失败"); }
    finally { setBusy(""); }
  }

  async function updateDay(event: FormEvent<HTMLFormElement>, day: Day) {
    event.preventDefault();
    if (busy || !canEdit) return;
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form).entries());
    setBusy(`day-${day.id}`); setError("");
    try {
      await api(`v1/pm/education/cohorts/${cohortId}/schedule/${day.id}`, { method: "PATCH", body: JSON.stringify({ ...values, version: day.version }) }, token);
      setMessage("课表日期已调整并保留审计记录。"); setRevision((value) => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "课表调整失败"); }
    finally { setBusy(""); }
  }

  async function createLog(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !canEdit) return;
    const form = event.currentTarget;
    const formData = new FormData(form);
    const values = Object.fromEntries(formData.entries());
    logId.current ||= crypto.randomUUID();
    const body = { ...values, request_id: logId.current, student_ids: formData.getAll("student_ids").map(String) };
    setBusy("log"); setError("");
    try {
      await api(`v1/pm/education/cohorts/${cohortId}/daily-logs`, { method: "POST", body: JSON.stringify(body) }, token);
      logId.current = null; form.reset(); setMessage("每日记录已保存。"); setRevision((value) => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "每日记录保存失败"); }
    finally { setBusy(""); }
  }

  async function updateLog(event: FormEvent<HTMLFormElement>, item: DailyLog) {
    event.preventDefault();
    if (busy || !canEdit) return;
    const formData = new FormData(event.currentTarget);
    const values = Object.fromEntries(formData.entries());
    const body = { ...values, student_ids: formData.getAll("student_ids").map(String), version: item.version };
    setBusy(`log-${item.id}`); setError("");
    try {
      await api(`v1/pm/education/cohorts/${cohortId}/daily-logs/${item.id}`, { method: "PATCH", body: JSON.stringify(body) }, token);
      setMessage("每日记录已修正并保留审计记录。"); setRevision((value) => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "每日记录修正失败"); }
    finally { setBusy(""); }
  }

  async function createCost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !canEdit) return;
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form).entries());
    costId.current ||= crypto.randomUUID();
    const month = String(values.allocation_month || "");
    const body = {
      ...values,
      request_id: costId.current,
      allocation_mode: allocationMode,
      allocation_month: month ? `${month}-01` : null,
      allocations: allocationMode === "custom" ? customAllocations.map((item) => ({
        ...item, allocation_month: `${item.allocation_month}-01`,
      })) : [],
    };
    setBusy("cost"); setError("");
    try {
      await api(`v1/pm/education/cohorts/${cohortId}/cost-documents`, { method: "POST", body: JSON.stringify(body) }, token);
      costId.current = null; form.reset(); setCategory("住宿费"); setAllocationMode("cohort");
      setCustomAllocations([{ cohort_id: cohortId, allocation_month: today().slice(0, 7), amount: "", note: "" }]);
      setMessage("成本单据已保存并完成分摊，班期总支出已同步更新。"); setRevision((value) => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "成本单据保存失败"); }
    finally { setBusy(""); }
  }

  async function loadCostForEdit(documentId: string) {
    if (busy) return;
    setBusy(`cost-load-${documentId}`); setError("");
    try {
      const item = await api<CostDetail>(`v1/pm/education/cohorts/${cohortId}/cost-documents/${documentId}`, {}, token);
      setEditingCost(item); setEditCategory(item.category); setEditAllocationMode(item.allocation_mode);
      setEditAllocations(item.allocations.map((allocation) => ({
        cohort_id: allocation.cohort_id,
        allocation_month: allocation.allocation_month.slice(0, 7),
        amount: allocation.amount,
        note: allocation.note || "",
      })));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "成本单据加载失败"); }
    finally { setBusy(""); }
  }

  async function updateCost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingCost || busy || !editingCost.can_edit) return;
    const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    const month = String(values.allocation_month || "");
    const body = {
      ...values,
      version: editingCost.version,
      allocation_mode: editAllocationMode,
      allocation_month: month ? `${month}-01` : null,
      allocations: editAllocationMode === "custom" ? editAllocations.map((item) => ({
        ...item, allocation_month: `${item.allocation_month}-01`,
      })) : [],
    };
    setBusy(`cost-update-${editingCost.id}`); setError("");
    try {
      await api(`v1/pm/education/cohorts/${cohortId}/cost-documents/${editingCost.id}`, { method: "PATCH", body: JSON.stringify(body) }, token);
      setEditingCost(null); setMessage("成本单据及分摊已修正，历史修改已写入审计记录。"); setRevision((value) => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "成本单据修正失败"); }
    finally { setBusy(""); }
  }

  const visibleLogs = (data?.logs || []).filter((item) =>
    (!logTypeFilter || item.log_type === logTypeFilter) && (!staffFilter || item.staff_id === staffFilter));

  return <section className="educationOperations">
    <header><div><p className="eyebrow">COHORT OPERATIONS</p><h3>班期运营台账</h3><p>原始成本只记一次；分摊用于明确班期、月份和学员归属，不重复增加总支出。</p></div></header>
    {error && <div className="educationError" role="alert">{error}</div>}
    {message && <div className="noticeBar" role="status">{message}</div>}

    <details className="educationOperationSection" open>
      <summary>6＋1 教学日历</summary>
      <div className="educationOperationSummary"><span>授课 {data?.schedule.summary.teaching || 0} 天</span><span>自主练习 {data?.schedule.summary.practice || 0} 天</span><span>休息/调整 {data?.schedule.summary.rest || 0} 天</span></div>
      {canEdit && <button type="button" className="secondaryButton" disabled={!!busy} onClick={() => void generateSchedule()}>{data?.schedule.generated ? "补齐缺失日期（不覆盖调整）" : "按6＋1生成完整课表"}</button>}
      <div className="educationCalendarGrid">{data?.schedule.days.map((day) => <form key={day.id} onSubmit={(event) => void updateDay(event, day)} className={`educationCalendarDay ${day.day_type}`}>
        <strong>第{day.day_number}天 · {day.calendar_date}</strong>
        <select name="day_type" defaultValue={day.day_type} disabled={!canEdit}><option value="teaching">授课日</option><option value="practice">自主练习日</option><option value="rest">休息/调整</option></select>
        <input name="title" defaultValue={day.title} maxLength={160} disabled={!canEdit} aria-label={`${day.calendar_date}安排`} />
        <input name="notes" defaultValue={day.notes} maxLength={2000} placeholder="课程重点/调整说明" disabled={!canEdit} />
        {canEdit && <button disabled={!!busy}>{busy === `day-${day.id}` ? "保存中…" : "保存"}</button>}
      </form>)}</div>
      {!data?.schedule.days.length && <p className="educationHint">尚未生成课表。系统会以开班日为第1天，循环安排6天授课、1天自主练习。</p>}
    </details>

    <details className="educationOperationSection" open>
      <summary>成本原始单据与分摊</summary>
      <div className="educationOperationSummary"><span>原始单据合计 {money(data?.costs.source_total || "0")}</span><span>分摊到本期 {money(data?.costs.allocated_to_cohort || "0")}</span></div>
      {canEdit && <form className="educationForm" onSubmit={(event) => void createCost(event)}>
        <label>发生日期<input name="occurred_on" type="date" defaultValue={today()} required /></label>
        <label>成本分类<select name="category" value={category} onChange={(event) => setCategory(event.target.value)}>{Object.keys(costDetails).map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>成本明细<select name="detail" key={category}>{costDetails[category].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>金额<input name="amount" type="number" min="0.01" step="0.01" required /></label>
        <label>分摊方式<select name="allocation_mode" value={allocationMode} onChange={(event) => setAllocationMode(event.target.value as typeof allocationMode)}><option value="cohort">本班期公共成本</option><option value="equal_students">均摊至本期在册学员</option><option value="custom">跨班期自定义分摊</option></select></label>
        <label>归属月份<input name="allocation_month" type="month" /></label>
        <label>供应商/收款方<input name="vendor" maxLength={240} /></label>
        <label>单据编号<input name="document_no" maxLength={120} /></label>
        <label className="educationWide">凭证位置或附件引用<input name="source_ref" maxLength={2000} placeholder="填写NAS路径、发票号或审批单链接；不会把原件上传到云端" /></label>
        <label className="educationWide">备注<textarea name="note" maxLength={2000} /></label>
        {allocationMode === "custom" && <div className="educationWide educationCustomAllocations">
          <strong>跨班期分摊明细（合计必须等于单据金额）</strong>
          {customAllocations.map((item, index) => <div key={index} className="educationCustomAllocationRow">
            <select value={item.cohort_id} onChange={(event) => setCustomAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, cohort_id: event.target.value } : row))}>{cohorts.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name}</option>)}</select>
            <input type="month" value={item.allocation_month} onChange={(event) => setCustomAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, allocation_month: event.target.value } : row))} required />
            <input type="number" min="0.01" step="0.01" placeholder="分摊金额" value={item.amount} onChange={(event) => setCustomAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, amount: event.target.value } : row))} required />
            <input placeholder="分摊说明" value={item.note} onChange={(event) => setCustomAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, note: event.target.value } : row))} />
            <button type="button" disabled={customAllocations.length === 1} onClick={() => setCustomAllocations((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}>移除</button>
          </div>)}
          <button type="button" onClick={() => setCustomAllocations((rows) => [...rows, { cohort_id: cohortId, allocation_month: today().slice(0, 7), amount: "", note: "" }])}>＋增加分摊行</button>
        </div>}
        <button className="primaryButton" disabled={!!busy}>{busy === "cost" ? "保存中…" : "保存成本并分摊"}</button>
      </form>}
      <div className="educationCostDocuments">{data?.costs.items.map((item) => <article key={item.id}>
        <header><strong>{item.category} / {item.detail}</strong><b>{money(item.amount)}</b></header>
        <p>{item.occurred_on}{item.vendor ? ` · ${item.vendor}` : ""}{item.document_no ? ` · 单据 ${item.document_no}` : ""}</p>
        <p>本期已分摊 {money(item.allocated_amount)} · {item.allocations.some((allocation) => allocation.student_id) ? `${item.allocations.length}名学员` : "班期公共成本"}</p>
        {item.source_ref && <p className="educationHint">凭证：{item.source_ref}</p>}
        {canEdit && <button type="button" disabled={!!busy} onClick={() => void loadCostForEdit(item.id)}>{busy === `cost-load-${item.id}` ? "加载中…" : "修正单据与分摊"}</button>}
      </article>)}</div>
      {editingCost && <section className="educationCostCorrection">
        <h4>修正成本单据</h4>
        {!editingCost.can_edit && <p className="educationError">该单据包含当前账号不可管理的班期分摊，请由L5管理修正。</p>}
        <form className="educationForm" onSubmit={(event) => void updateCost(event)}>
          <label>发生日期<input name="occurred_on" type="date" defaultValue={editingCost.occurred_on} required disabled={!editingCost.can_edit} /></label>
          <label>成本分类<select name="category" value={editCategory} onChange={(event) => setEditCategory(event.target.value)} disabled={!editingCost.can_edit}>{Object.keys(costDetails).map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>成本明细<select name="detail" key={editCategory} defaultValue={editingCost.category === editCategory ? editingCost.detail : costDetails[editCategory][0]} disabled={!editingCost.can_edit}>{costDetails[editCategory].map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>金额<input name="amount" type="number" min="0.01" step="0.01" defaultValue={editingCost.amount} required disabled={!editingCost.can_edit} /></label>
          <label>分摊方式<select name="allocation_mode" value={editAllocationMode} onChange={(event) => { const mode = event.target.value as typeof editAllocationMode; setEditAllocationMode(mode); if (mode === "custom" && editAllocationMode !== "custom") setEditAllocations([{ cohort_id: cohortId, allocation_month: editingCost.occurred_on.slice(0, 7), amount: editingCost.amount, note: editingCost.note }]); }} disabled={!editingCost.can_edit}><option value="cohort">本班期公共成本</option><option value="equal_students">均摊至本期在册学员</option><option value="custom">跨班期自定义分摊</option></select></label>
          <label>归属月份<input name="allocation_month" type="month" defaultValue={editingCost.allocation_month?.slice(0, 7) || editingCost.occurred_on.slice(0, 7)} disabled={!editingCost.can_edit} /></label>
          <label>供应商/收款方<input name="vendor" defaultValue={editingCost.vendor} maxLength={240} disabled={!editingCost.can_edit} /></label>
          <label>单据编号<input name="document_no" defaultValue={editingCost.document_no} maxLength={120} disabled={!editingCost.can_edit} /></label>
          <label className="educationWide">凭证位置或附件引用<input name="source_ref" defaultValue={editingCost.source_ref} maxLength={2000} disabled={!editingCost.can_edit} /></label>
          <label className="educationWide">备注<textarea name="note" defaultValue={editingCost.note} maxLength={2000} disabled={!editingCost.can_edit} /></label>
          {editAllocationMode === "custom" && <div className="educationWide educationCustomAllocations">{editAllocations.map((item, index) => <div key={index} className="educationCustomAllocationRow">
            <select value={item.cohort_id} onChange={(event) => setEditAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, cohort_id: event.target.value } : row))}>{cohorts.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name}</option>)}</select>
            <input type="month" value={item.allocation_month} onChange={(event) => setEditAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, allocation_month: event.target.value } : row))} required />
            <input type="number" min="0.01" step="0.01" value={item.amount} onChange={(event) => setEditAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, amount: event.target.value } : row))} required />
            <input value={item.note} placeholder="分摊说明" onChange={(event) => setEditAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, note: event.target.value } : row))} />
            <button type="button" disabled={editAllocations.length === 1} onClick={() => setEditAllocations((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}>移除</button>
          </div>)}<button type="button" onClick={() => setEditAllocations((rows) => [...rows, { cohort_id: cohortId, allocation_month: editingCost.occurred_on.slice(0, 7), amount: "", note: "" }])}>＋增加分摊行</button></div>}
          <button className="primaryButton" disabled={!!busy || !editingCost.can_edit}>{busy === `cost-update-${editingCost.id}` ? "保存中…" : "保存修正"}</button>
          <button type="button" disabled={!!busy} onClick={() => setEditingCost(null)}>取消</button>
        </form>
      </section>}
      {!data?.costs.items.length && <p className="educationHint">尚未登记结构化成本单据。原有“公共收支”仍保留，不会被自动重复迁移。</p>}
    </details>

    {data?.can_view_logs && <details className="educationOperationSection" open>
      <summary>教学与生活每日记录</summary>
      {!!data.missing_log_days.length && <div className="educationMissingLogs" role="status"><strong>缺报提醒：{data.missing_log_days.length}天</strong><span>{data.missing_log_days.slice(0, 8).join("、")}{data.missing_log_days.length > 8 ? "…" : ""}</span></div>}
      {canEdit && <form className="educationForm" onSubmit={(event) => void createLog(event)}>
        <label>记录日期<input name="log_date" type="date" defaultValue={today()} required /></label>
        <label>记录人员<select name="staff_id" required defaultValue=""><option value="" disabled>选择在册人员</option>{staff.filter((item) => item.active).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.role}</option>)}</select></label>
        <label>记录类型<select name="log_type"><option>教学记录</option><option>自主练习</option><option>考勤记录</option><option>生活管理</option><option>异常事件</option></select></label>
        <label>关联学员（可多选）<select name="student_ids" multiple size={Math.min(5, Math.max(2, students.length))}>{students.map((item) => <option key={item.id} value={item.id}>{item.student_no ? `${item.student_no} · ` : ""}{item.name}</option>)}</select></label>
        <label className="educationWide">客观记录<textarea name="summary" required minLength={2} maxLength={5000} placeholder="记录实际发生的教学、训练、考勤或生活情况，避免笼统评价" /></label>
        <label className="educationWide">后续动作<textarea name="follow_up" maxLength={3000} placeholder="需要跟进、纠偏或与家长沟通的事项" /></label>
        <button className="primaryButton" disabled={!!busy || !staff.some((item) => item.active)}>{busy === "log" ? "保存中…" : "保存每日记录"}</button>
      </form>}
      <div className="educationLogFilters"><label>按类型筛选<select value={logTypeFilter} onChange={(event) => setLogTypeFilter(event.target.value)}><option value="">全部类型</option><option>教学记录</option><option>自主练习</option><option>考勤记录</option><option>生活管理</option><option>异常事件</option></select></label><label>按人员筛选<select value={staffFilter} onChange={(event) => setStaffFilter(event.target.value)}><option value="">全部人员</option>{staff.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.role}</option>)}</select></label></div>
      <div className="educationDailyLogs">{visibleLogs.map((item) => <article key={item.id}><header><strong>{item.log_date} · {item.log_type}</strong><span>{item.staff_name}（{item.staff_role}）</span></header><p>{item.summary}</p>{item.follow_up && <p><b>后续：</b>{item.follow_up}</p>}{canEdit && <details><summary>修正记录</summary><form className="educationForm" onSubmit={(event) => void updateLog(event, item)}>
        <label>记录日期<input name="log_date" type="date" defaultValue={item.log_date} required /></label>
        <label>记录人员<select name="staff_id" defaultValue={item.staff_id}>{staff.filter((person) => person.active || person.id === item.staff_id).map((person) => <option key={person.id} value={person.id}>{person.name} · {person.role}</option>)}</select></label>
        <label>记录类型<select name="log_type" defaultValue={item.log_type}><option>教学记录</option><option>自主练习</option><option>考勤记录</option><option>生活管理</option><option>异常事件</option></select></label>
        <label>关联学员<select name="student_ids" multiple size={Math.min(5, Math.max(2, students.length))} defaultValue={item.student_ids}>{students.map((student) => <option key={student.id} value={student.id}>{student.name}</option>)}</select></label>
        <label className="educationWide">客观记录<textarea name="summary" defaultValue={item.summary} required minLength={2} maxLength={5000} /></label>
        <label className="educationWide">后续动作<textarea name="follow_up" defaultValue={item.follow_up} maxLength={3000} /></label>
        <button disabled={!!busy}>{busy === `log-${item.id}` ? "保存中…" : "保存修正"}</button>
      </form></details>}</article>)}</div>
      {!visibleLogs.length && <p className="educationHint">当前筛选条件下没有每日记录。</p>}
    </details>}
  </section>;
}
