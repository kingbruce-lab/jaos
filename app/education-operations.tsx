"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

type Api = <T>(path: string, options?: RequestInit, token?: string) => Promise<T>;
type DayReport = { instructor_ids: string[]; student_ids: string[]; attendance: string; lesson_objectives: string; lesson_content: string; student_performance: string; issues_and_adjustments: string; homework_or_practice: string; parent_communication: string; next_plan: string; special_achievement: boolean; special_achievement_note: string; problem_flag: boolean; problem_note: string };
type Day = { id: string; calendar_date: string; day_number: number; day_type: "teaching" | "practice" | "rest"; title: string; notes: string; report: DayReport; version: number };
type CostAllocation = { id: string; cohort_id: string; cohort_name?: string; student_id: string | null; student_name: string | null; allocation_month: string; amount: string; note?: string };
type CostAttachment = { id: string; filename: string; size_bytes: number; sha256: string; created_at: string };
type Cost = { id: string; occurred_on: string; ended_on: string; category: string; detail: string; amount: string; allocated_amount: string; vendor: string; document_no: string; source_ref: string; note: string; allocations: CostAllocation[]; attachments: CostAttachment[]; version: number };
type CostDetail = Cost & { allocation_mode: "cohort" | "equal_students" | "custom"; allocation_month: string | null; can_edit: boolean; has_hidden_allocations: boolean };
type DailyLog = { id: string; log_date: string; staff_id: string; staff_name: string; staff_role: string; log_type: string; summary: string; follow_up: string; student_ids: string[]; version: number };
type MonthlySummary = { id?: string; month: string; summary: string; achievements: string; problems: string; next_month_plan: string; version: number };
type Operations = { schedule: { generated: boolean; days: Day[]; monthly_summaries: MonthlySummary[]; summary: { teaching: number; practice: number; rest: number } }; costs: { items: Cost[]; source_total: string; allocated_to_cohort: string }; logs: DailyLog[]; missing_log_days: string[]; can_view_logs: boolean; can_edit: boolean };
type Staff = { id: string; name: string; role: string; active: boolean };
type Student = { id: string; name: string; student_no?: string | null };
type CohortOption = { id: string; name: string };
type CustomAllocation = { cohort_id: string; amount: string; note: string };

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

export function EducationOperations({ api, token, cohortId, cohortStart, cohortEnd, canEdit, cohorts, onChanged }: { api: Api; token: string; cohortId: string; cohortStart: string; cohortEnd: string; canEdit: boolean; cohorts: CohortOption[]; onChanged: () => void }) {
  const [data, setData] = useState<Operations | null>(null);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [category, setCategory] = useState("住宿费");
  const [allocationMode, setAllocationMode] = useState<"cohort" | "equal_students" | "custom">("cohort");
  const [customAllocations, setCustomAllocations] = useState<CustomAllocation[]>([{ cohort_id: cohortId, amount: "", note: "" }]);
  const [logTypeFilter, setLogTypeFilter] = useState("");
  const [staffFilter, setStaffFilter] = useState("");
  const [editingCost, setEditingCost] = useState<CostDetail | null>(null);
  const [selectedDayId, setSelectedDayId] = useState("");
  const [selectedMonth, setSelectedMonth] = useState("");
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
      setRevision((value) => value + 1); onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "生成课表失败"); }
    finally { setBusy(""); }
  }

  async function updateDay(event: FormEvent<HTMLFormElement>, day: Day) {
    event.preventDefault();
    if (busy || !canEdit) return;
    const form = event.currentTarget;
    const formData = new FormData(form);
    const values = Object.fromEntries(formData.entries());
    const report = {
      instructor_ids: formData.getAll("instructor_ids").map(String),
      student_ids: formData.getAll("student_ids").map(String),
      attendance: String(values.attendance || ""), lesson_objectives: String(values.lesson_objectives || ""),
      lesson_content: String(values.lesson_content || ""), student_performance: String(values.student_performance || ""),
      issues_and_adjustments: String(values.issues_and_adjustments || ""), homework_or_practice: String(values.homework_or_practice || ""),
      parent_communication: String(values.parent_communication || ""), next_plan: String(values.next_plan || ""),
      special_achievement: formData.has("special_achievement"), special_achievement_note: String(values.special_achievement_note || ""),
      problem_flag: formData.has("problem_flag"), problem_note: String(values.problem_note || ""),
    };
    ["instructor_ids", "student_ids", "attendance", "lesson_objectives", "lesson_content", "student_performance", "issues_and_adjustments", "homework_or_practice", "parent_communication", "next_plan", "special_achievement", "special_achievement_note", "problem_flag", "problem_note"].forEach((key) => delete values[key]);
    setBusy(`day-${day.id}`); setError("");
    try {
      await api(`v1/pm/education/cohorts/${cohortId}/schedule/${day.id}`, { method: "PATCH", body: JSON.stringify({ ...values, report, version: day.version }) }, token);
      setMessage(`${day.calendar_date} 的教学日报已保存。`); setRevision((value) => value + 1); onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "课表调整失败"); }
    finally { setBusy(""); }
  }

  async function updateMonthlySummary(event: FormEvent<HTMLFormElement>, month: string) {
    event.preventDefault();
    if (busy || !canEdit) return;
    const current = data?.schedule.monthly_summaries.find((item) => item.month === month);
    const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    setBusy(`month-${month}`); setError("");
    try {
      await api(`v1/pm/education/cohorts/${cohortId}/monthly-summaries/${month}`, { method: "PUT", body: JSON.stringify({ ...values, version: current?.version || 0 }) }, token);
      setMessage(`${month} 月度总结已保存。`); setRevision((value) => value + 1); onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "月度总结保存失败"); }
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
      logId.current = null; form.reset(); setMessage("每日记录已保存。"); setRevision((value) => value + 1); onChanged();
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
      setMessage("每日记录已修正并保留审计记录。"); setRevision((value) => value + 1); onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "每日记录修正失败"); }
    finally { setBusy(""); }
  }

  async function createCost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !canEdit) return;
    const form = event.currentTarget;
    const formData = new FormData(form);
    const values = Object.fromEntries(formData.entries());
    const attachments = formData.getAll("attachments").filter((item): item is File => item instanceof File && item.size > 0);
    delete values.attachments;
    costId.current ||= crypto.randomUUID();
    const occurredOn = String(values.occurred_on || cohortStart);
    const body = {
      ...values,
      request_id: costId.current,
      allocation_mode: allocationMode,
      allocation_month: null,
      allocations: allocationMode === "custom" ? customAllocations.map((item) => ({
        ...item, allocation_month: `${occurredOn.slice(0, 7)}-01`,
      })) : [],
    };
    setBusy("cost"); setError("");
    try {
      const result = await api<{ id: string }>(`v1/pm/education/cohorts/${cohortId}/cost-documents`, { method: "POST", body: JSON.stringify(body) }, token);
      for (const attachment of attachments) await uploadAttachment(result.id, attachment);
      costId.current = null; form.reset(); setCategory("住宿费"); setAllocationMode("cohort");
      setCustomAllocations([{ cohort_id: cohortId, amount: "", note: "" }]);
      setMessage(`费用时段已保存${attachments.length ? `，并上传 ${attachments.length} 个凭证附件` : ""}，顶部汇总已刷新。`); setRevision((value) => value + 1); onChanged();
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
        amount: allocation.amount,
        note: allocation.note || "",
      })));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "成本单据加载失败"); }
    finally { setBusy(""); }
  }

  async function updateCost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingCost || busy || !editingCost.can_edit) return;
    const formData = new FormData(event.currentTarget);
    const values = Object.fromEntries(formData.entries());
    const attachments = formData.getAll("attachments").filter((item): item is File => item instanceof File && item.size > 0);
    delete values.attachments;
    const occurredOn = String(values.occurred_on || editingCost.occurred_on);
    const body = {
      ...values,
      version: editingCost.version,
      allocation_mode: editAllocationMode,
      allocation_month: null,
      allocations: editAllocationMode === "custom" ? editAllocations.map((item) => ({
        ...item, allocation_month: `${occurredOn.slice(0, 7)}-01`,
      })) : [],
    };
    setBusy(`cost-update-${editingCost.id}`); setError("");
    try {
      await api(`v1/pm/education/cohorts/${cohortId}/cost-documents/${editingCost.id}`, { method: "PATCH", body: JSON.stringify(body) }, token);
      for (const attachment of attachments) await uploadAttachment(editingCost.id, attachment);
      setEditingCost(null); setMessage("费用时段及附件已更新，顶部汇总已刷新。"); setRevision((value) => value + 1); onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "成本单据修正失败"); }
    finally { setBusy(""); }
  }

  async function uploadAttachment(documentId: string, file: File) {
    const body = new FormData(); body.set("file", file);
    await api(`v1/pm/education/cohorts/${cohortId}/cost-documents/${documentId}/attachments`, { method: "POST", body }, token);
  }

  async function downloadAttachment(documentId: string, attachment: CostAttachment) {
    setBusy(`attachment-download-${attachment.id}`); setError("");
    try {
      const response = await fetch(`/api/kb/v1/pm/education/cohorts/${cohortId}/cost-documents/${documentId}/attachments/${attachment.id}`, { headers: { authorization: `Bearer ${token}` }, cache: "no-store" });
      if (!response.ok) throw new Error(`附件下载失败（${response.status}）`);
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = attachment.filename; anchor.click(); URL.revokeObjectURL(url);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "附件下载失败"); }
    finally { setBusy(""); }
  }

  async function deleteAttachment(documentId: string, attachment: CostAttachment) {
    if (busy || !canEdit || !confirm(`确认移除凭证“${attachment.filename}”？`)) return;
    setBusy(`attachment-delete-${attachment.id}`); setError("");
    try {
      await api(`v1/pm/education/cohorts/${cohortId}/cost-documents/${documentId}/attachments/${attachment.id}`, { method: "DELETE" }, token);
      setMessage("凭证附件已移除。"); setRevision((value) => value + 1); onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "附件移除失败"); }
    finally { setBusy(""); }
  }

  const visibleLogs = (data?.logs || []).filter((item) =>
    (!logTypeFilter || item.log_type === logTypeFilter) && (!staffFilter || item.staff_id === staffFilter));
  const selectedDay = data?.schedule.days.find((day) => day.id === selectedDayId);
  const reportComplete = (day: Day) => Boolean(day.report?.lesson_content || day.report?.student_performance || day.report?.attendance);
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const monthGroups = Array.from((data?.schedule.days || []).reduce((groups, day) => {
    const month = day.calendar_date.slice(0, 7);
    groups.set(month, [...(groups.get(month) || []), day]);
    return groups;
  }, new Map<string, Day[]>()).entries());
  const selectedSummary = data?.schedule.monthly_summaries.find((item) => item.month === selectedMonth);

  return <section className="educationOperations">
    <header><div><p className="eyebrow">COHORT OPERATIONS</p><h3>班期运营台账</h3><p>原始成本只记一次；分摊用于明确班期、月份和学员归属，不重复增加总支出。</p></div></header>
    {error && <div className="educationError" role="alert">{error}</div>}
    {message && <div className="noticeBar" role="status">{message}</div>}

    <section className="educationOperationSection educationCalendarSection">
      <h4 className="educationSectionTitle">6＋1 教学日历</h4>
      <div className="educationOperationSummary"><span>授课 {data?.schedule.summary.teaching || 0} 天</span><span>自主练习 {data?.schedule.summary.practice || 0} 天</span><span>休息/调整 {data?.schedule.summary.rest || 0} 天</span></div>
      {canEdit && <button type="button" className="secondaryButton" disabled={!!busy} onClick={() => void generateSchedule()}>{data?.schedule.generated ? "补齐缺失日期（不覆盖调整）" : "按6＋1生成完整课表"}</button>}
      {!!data?.missing_log_days.length && <div className="educationMissingLogs" role="status"><strong>日报待填：{data.missing_log_days.length}天</strong><span>{data.missing_log_days.slice(0, 8).join("、")}{data.missing_log_days.length > 8 ? "…" : ""}</span></div>}
      <p className="educationHint">点击任意日期，会在下方打开完整的每日报告。日历用于每天的主记录；临时异常或多位老师的补充事项可在页面末尾另行追加。</p>
      <div className="educationCalendarMonths">{monthGroups.map(([month, days]) => {
        const firstWeekday = new Date(`${days[0].calendar_date}T00:00:00`).getDay();
        const summary = data?.schedule.monthly_summaries.find((item) => item.month === month);
        const completed = days.filter(reportComplete).length;
        const achievements = days.filter((day) => day.report.special_achievement).length;
        const problems = days.filter((day) => day.report.problem_flag).length;
        return <section className="educationCalendarMonth" key={month}>
          <header><h5>{month.slice(0, 4)} 年 {Number(month.slice(5))} 月</h5><span>已填日报 {completed}/{days.length}</span></header>
          <div className="educationCalendarScroller">
            <div className="educationWeekdayRow">{weekdays.map((weekday) => <b key={weekday}>{weekday}</b>)}</div>
            <div className="educationCalendarGrid">
              {Array.from({ length: firstWeekday }).map((_, index) => <span className="educationCalendarBlank" aria-hidden="true" key={`blank-${index}`} />)}
              {days.map((day) => <article key={day.id} className={`educationCalendarDay ${day.day_type} ${selectedDayId === day.id ? "selected" : ""}`}>
                <button type="button" className="educationDayOpen" onClick={() => { setSelectedDayId(day.id); setSelectedMonth(""); }}>
                  <strong>{Number(day.calendar_date.slice(8))}日 · 第{day.day_number}天</strong>
                  <span>{day.day_type === "teaching" ? "授课日" : day.day_type === "practice" ? "自主练习日" : "休息/调整"}</span>
                  <b>{day.title || "未填写安排"}</b>
                  <small>{reportComplete(day) ? "日报已填写" : "点击填写日报"}</small>
                </button>
                <div className="educationDayMarks">
                  <button type="button" className={day.report.special_achievement ? "active" : ""} title="特殊成绩日" aria-label="特殊成绩日" onClick={() => { setSelectedDayId(day.id); setSelectedMonth(""); }}>★</button>
                  <button type="button" className={day.report.problem_flag ? "active" : ""} title="出现问题日" aria-label="出现问题日" onClick={() => { setSelectedDayId(day.id); setSelectedMonth(""); }}>?</button>
                </div>
              </article>)}
              <button type="button" className={`educationMonthlySummaryCard ${summary?.summary ? "complete" : ""}`} onClick={() => { setSelectedMonth(month); setSelectedDayId(""); }}>
                <strong>{Number(month.slice(5))} 月月度总结</strong>
                <span>红星 {achievements} 天 · 问题 {problems} 天</span>
                <small>{summary?.summary ? "已填写 · 点击查看或修正" : "本月最后一格 · 点击填写"}</small>
              </button>
            </div>
          </div>
        </section>;
      })}</div>
      {selectedDay && <form key={`${selectedDay.id}-${selectedDay.version}`} onSubmit={(event) => void updateDay(event, selectedDay)} className="educationDayEditor">
        <header><div><span>第 {selectedDay.day_number} 天</span><h4>{selectedDay.calendar_date} 教学日报</h4></div><button type="button" onClick={() => setSelectedDayId("")}>关闭</button></header>
        <div className="educationForm">
          <label>日期类型<select name="day_type" defaultValue={selectedDay.day_type} disabled={!canEdit}><option value="teaching">授课日</option><option value="practice">自主练习日</option><option value="rest">休息/调整</option></select></label>
          <label>当日主题<input name="title" defaultValue={selectedDay.title} maxLength={160} disabled={!canEdit} /></label>
          <label>授课教师 / 助教（可多选）<select name="instructor_ids" multiple size={Math.min(6, Math.max(3, staff.length))} defaultValue={selectedDay.report?.instructor_ids || []} disabled={!canEdit}>{staff.filter((item) => item.active || selectedDay.report?.instructor_ids.includes(item.id)).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.role}</option>)}</select></label>
          <label>关联学员（可多选）<select name="student_ids" multiple size={Math.min(6, Math.max(3, students.length))} defaultValue={selectedDay.report?.student_ids || []} disabled={!canEdit}>{students.map((item) => <option key={item.id} value={item.id}>{item.student_no ? `${item.student_no} · ` : ""}{item.name}</option>)}</select></label>
          <label className="educationWide">出勤与状态<textarea name="attendance" defaultValue={selectedDay.report?.attendance} maxLength={2000} disabled={!canEdit} placeholder="到课、迟到、请假、精神及身体状态等客观情况" /></label>
          <label className="educationWide">课程目标<textarea name="lesson_objectives" defaultValue={selectedDay.report?.lesson_objectives} maxLength={3000} disabled={!canEdit} placeholder="今天计划达成的知识、操作或训练目标" /></label>
          <label className="educationWide">教学内容与训练安排<textarea name="lesson_content" defaultValue={selectedDay.report?.lesson_content} maxLength={5000} disabled={!canEdit} placeholder="实际讲授内容、训练项目、时长和完成情况" /></label>
          <label className="educationWide">学员表现与进步<textarea name="student_performance" defaultValue={selectedDay.report?.student_performance} maxLength={5000} disabled={!canEdit} placeholder="记录具体表现、数据变化和可验证的进步" /></label>
          <label className="educationWide">问题、纠偏与调整<textarea name="issues_and_adjustments" defaultValue={selectedDay.report?.issues_and_adjustments} maxLength={5000} disabled={!canEdit} placeholder="出现的问题、采取的处理以及课程节奏调整" /></label>
          <label className="educationWide">课后作业 / 自主练习<textarea name="homework_or_practice" defaultValue={selectedDay.report?.homework_or_practice} maxLength={3000} disabled={!canEdit} /></label>
          <label className="educationWide">家长沟通记录<textarea name="parent_communication" defaultValue={selectedDay.report?.parent_communication} maxLength={3000} disabled={!canEdit} placeholder="仅记录客观沟通内容及已确认事项" /></label>
          <label className="educationWide">次日计划<textarea name="next_plan" defaultValue={selectedDay.report?.next_plan} maxLength={3000} disabled={!canEdit} /></label>
          <div className="educationWide educationDayFlagGrid">
            <label className="educationDayFlag"><span><input type="checkbox" name="special_achievement" defaultChecked={selectedDay.report?.special_achievement} disabled={!canEdit} /> <b>★ 特殊成绩日</b></span><textarea name="special_achievement_note" defaultValue={selectedDay.report?.special_achievement_note} maxLength={2000} disabled={!canEdit} placeholder="记录突破、比赛成绩、阶段性进步及可验证依据" /></label>
            <label className="educationDayFlag problem"><span><input type="checkbox" name="problem_flag" defaultChecked={selectedDay.report?.problem_flag} disabled={!canEdit} /> <b>? 出现问题日</b></span><textarea name="problem_note" defaultValue={selectedDay.report?.problem_note} maxLength={2000} disabled={!canEdit} placeholder="记录问题、影响、处理结果及需要继续跟进的事项" /></label>
          </div>
          <label className="educationWide">日程调整说明<textarea name="notes" defaultValue={selectedDay.notes} maxLength={2000} disabled={!canEdit} placeholder="临时调课、休息或其他日程说明" /></label>
          {canEdit && <button className="primaryButton" disabled={!!busy}>{busy === `day-${selectedDay.id}` ? "保存中…" : "保存本日完整报告"}</button>}
        </div>
      </form>}
      {selectedMonth && <form key={`${selectedMonth}-${selectedSummary?.version || 0}`} onSubmit={(event) => void updateMonthlySummary(event, selectedMonth)} className="educationDayEditor educationMonthlyEditor">
        <header><div><span>MONTHLY REVIEW</span><h4>{selectedMonth.slice(0, 4)} 年 {Number(selectedMonth.slice(5))} 月月度总结</h4></div><button type="button" onClick={() => setSelectedMonth("")}>关闭</button></header>
        <div className="educationForm">
          <label className="educationWide">本月教学与运营总结<textarea name="summary" defaultValue={selectedSummary?.summary || ""} maxLength={8000} disabled={!canEdit} placeholder="总结授课执行、学员状态、招生收费和班期运营情况" /></label>
          <label className="educationWide">本月成绩与亮点<textarea name="achievements" defaultValue={selectedSummary?.achievements || ""} maxLength={5000} disabled={!canEdit} placeholder="汇总红星日期的关键成果、数据和典型案例" /></label>
          <label className="educationWide">本月问题与纠偏<textarea name="problems" defaultValue={selectedSummary?.problems || ""} maxLength={5000} disabled={!canEdit} placeholder="汇总问题日期、原因、已采取措施和遗留风险" /></label>
          <label className="educationWide">下月计划<textarea name="next_month_plan" defaultValue={selectedSummary?.next_month_plan || ""} maxLength={5000} disabled={!canEdit} placeholder="下月课程、人员、招生、成本和家长沟通计划" /></label>
          {canEdit && <button className="primaryButton" disabled={!!busy}>{busy === `month-${selectedMonth}` ? "保存中…" : "保存月度总结"}</button>}
        </div>
      </form>}
      {!data?.schedule.days.length && <p className="educationHint">尚未生成课表。系统会以开班日为第1天，循环安排6天授课、1天自主练习。</p>}
    </section>

    <details className="educationOperationSection" open>
      <summary>分段费用、凭证与成本分摊</summary>
      <div className="educationOperationSummary"><span>原始单据合计 {money(data?.costs.source_total || "0")}</span><span>分摊到本期 {money(data?.costs.allocated_to_cohort || "0")}</span></div>
      {canEdit && <form className="educationForm" onSubmit={(event) => void createCost(event)}>
        <label>发生日期<input name="occurred_on" type="date" defaultValue={cohortStart} required /></label>
        <label>结束日期<input name="ended_on" type="date" defaultValue={cohortEnd} required /></label>
        <label>成本分类<select name="category" value={category} onChange={(event) => setCategory(event.target.value)}>{Object.keys(costDetails).map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>成本明细<select name="detail" key={category}>{costDetails[category].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>金额<input name="amount" type="number" min="0.01" step="0.01" required /></label>
        <label>分摊方式<select name="allocation_mode" value={allocationMode} onChange={(event) => setAllocationMode(event.target.value as typeof allocationMode)}><option value="cohort">本班期公共成本</option><option value="equal_students">均摊至本期在册学员</option><option value="custom">跨班期自定义分摊</option></select></label>
        <label>供应商/收款方<input name="vendor" maxLength={240} /></label>
        <label>单据编号<input name="document_no" maxLength={120} /></label>
        <label className="educationWide educationFileField">凭证与附件<input name="attachments" type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx,.zip" /><small>文件直接保存到公司 NAS 的台账附件目录；单个文件最大 200MB，可多选。</small></label>
        <label className="educationWide">备注<textarea name="note" maxLength={2000} /></label>
        {allocationMode === "custom" && <div className="educationWide educationCustomAllocations">
          <strong>跨班期分摊明细（合计必须等于单据金额）</strong>
          {customAllocations.map((item, index) => <div key={index} className="educationCustomAllocationRow">
            <select value={item.cohort_id} onChange={(event) => setCustomAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, cohort_id: event.target.value } : row))}>{cohorts.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name}</option>)}</select>
            <input type="number" min="0.01" step="0.01" placeholder="分摊金额" value={item.amount} onChange={(event) => setCustomAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, amount: event.target.value } : row))} required />
            <input placeholder="分摊说明" value={item.note} onChange={(event) => setCustomAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, note: event.target.value } : row))} />
            <button type="button" disabled={customAllocations.length === 1} onClick={() => setCustomAllocations((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}>移除</button>
          </div>)}
          <button type="button" onClick={() => setCustomAllocations((rows) => [...rows, { cohort_id: cohortId, amount: "", note: "" }])}>＋增加分摊行</button>
        </div>}
        <p className="educationWide educationHint">价格发生变化时，按不同起止日期分别保存一条费用时段，即可持续增加并保留每段价格。</p>
        <button className="primaryButton" disabled={!!busy}>{busy === "cost" ? "保存中…" : "保存并继续增加下一段费用"}</button>
      </form>}
      <div className="educationCostDocuments">{data?.costs.items.map((item) => <article key={item.id}>
        <header><strong>{item.category} / {item.detail}</strong><b>{money(item.amount)}</b></header>
        <p>发生 {item.occurred_on} · 结束 {item.ended_on || item.occurred_on}{item.vendor ? ` · ${item.vendor}` : ""}{item.document_no ? ` · 单据 ${item.document_no}` : ""}</p>
        <p>本期已分摊 {money(item.allocated_amount)} · {item.allocations.some((allocation) => allocation.student_id) ? `${item.allocations.length}名学员` : "班期公共成本"}</p>
        {item.source_ref && <p className="educationHint">凭证：{item.source_ref}</p>}
        {!!item.attachments.length && <div className="educationAttachments">{item.attachments.map((attachment) => <span key={attachment.id}><button type="button" disabled={!!busy} onClick={() => void downloadAttachment(item.id, attachment)}>{attachment.filename}</button><small>{Math.max(1, Math.ceil(attachment.size_bytes / 1024))} KB</small>{canEdit && <button type="button" className="educationAttachmentDelete" disabled={!!busy} onClick={() => void deleteAttachment(item.id, attachment)}>移除</button>}</span>)}</div>}
        {canEdit && <button type="button" disabled={!!busy} onClick={() => void loadCostForEdit(item.id)}>{busy === `cost-load-${item.id}` ? "加载中…" : "修正单据与分摊"}</button>}
      </article>)}</div>
      {editingCost && <section className="educationCostCorrection">
        <h4>修正成本单据</h4>
        {!editingCost.can_edit && <p className="educationError">该单据包含当前账号不可管理的班期分摊，请由L5管理修正。</p>}
        <form className="educationForm" onSubmit={(event) => void updateCost(event)}>
          <label>发生日期<input name="occurred_on" type="date" defaultValue={editingCost.occurred_on} required disabled={!editingCost.can_edit} /></label>
          <label>结束日期<input name="ended_on" type="date" defaultValue={editingCost.ended_on || editingCost.occurred_on} required disabled={!editingCost.can_edit} /></label>
          <label>成本分类<select name="category" value={editCategory} onChange={(event) => setEditCategory(event.target.value)} disabled={!editingCost.can_edit}>{Object.keys(costDetails).map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>成本明细<select name="detail" key={editCategory} defaultValue={editingCost.category === editCategory ? editingCost.detail : costDetails[editCategory][0]} disabled={!editingCost.can_edit}>{costDetails[editCategory].map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>金额<input name="amount" type="number" min="0.01" step="0.01" defaultValue={editingCost.amount} required disabled={!editingCost.can_edit} /></label>
          <label>分摊方式<select name="allocation_mode" value={editAllocationMode} onChange={(event) => { const mode = event.target.value as typeof editAllocationMode; setEditAllocationMode(mode); if (mode === "custom" && editAllocationMode !== "custom") setEditAllocations([{ cohort_id: cohortId, amount: editingCost.amount, note: editingCost.note }]); }} disabled={!editingCost.can_edit}><option value="cohort">本班期公共成本</option><option value="equal_students">均摊至本期在册学员</option><option value="custom">跨班期自定义分摊</option></select></label>
          <label>供应商/收款方<input name="vendor" defaultValue={editingCost.vendor} maxLength={240} disabled={!editingCost.can_edit} /></label>
          <label>单据编号<input name="document_no" defaultValue={editingCost.document_no} maxLength={120} disabled={!editingCost.can_edit} /></label>
          <label className="educationWide educationFileField">继续添加凭证与附件<input name="attachments" type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx,.zip" disabled={!editingCost.can_edit} /><small>新选择的文件将追加保存，原附件不会被覆盖。</small></label>
          <label className="educationWide">备注<textarea name="note" defaultValue={editingCost.note} maxLength={2000} disabled={!editingCost.can_edit} /></label>
          {editAllocationMode === "custom" && <div className="educationWide educationCustomAllocations">{editAllocations.map((item, index) => <div key={index} className="educationCustomAllocationRow">
            <select value={item.cohort_id} onChange={(event) => setEditAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, cohort_id: event.target.value } : row))}>{cohorts.map((cohort) => <option key={cohort.id} value={cohort.id}>{cohort.name}</option>)}</select>
            <input type="number" min="0.01" step="0.01" value={item.amount} onChange={(event) => setEditAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, amount: event.target.value } : row))} required />
            <input value={item.note} placeholder="分摊说明" onChange={(event) => setEditAllocations((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, note: event.target.value } : row))} />
            <button type="button" disabled={editAllocations.length === 1} onClick={() => setEditAllocations((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}>移除</button>
          </div>)}<button type="button" onClick={() => setEditAllocations((rows) => [...rows, { cohort_id: cohortId, amount: "", note: "" }])}>＋增加分摊行</button></div>}
          {!!editingCost.attachments.length && <div className="educationWide educationAttachments">{editingCost.attachments.map((attachment) => <span key={attachment.id}><button type="button" onClick={() => void downloadAttachment(editingCost.id, attachment)}>{attachment.filename}</button><small>{Math.max(1, Math.ceil(attachment.size_bytes / 1024))} KB</small>{editingCost.can_edit && <button type="button" className="educationAttachmentDelete" onClick={() => void deleteAttachment(editingCost.id, attachment)}>移除</button>}</span>)}</div>}
          <button className="primaryButton" disabled={!!busy || !editingCost.can_edit}>{busy === `cost-update-${editingCost.id}` ? "保存中…" : "保存修正"}</button>
          <button type="button" disabled={!!busy} onClick={() => setEditingCost(null)}>取消</button>
        </form>
      </section>}
      {!data?.costs.items.length && <p className="educationHint">尚未登记结构化成本单据。原有“公共收支”仍保留，不会被自动重复迁移。</p>}
    </details>

    {data?.can_view_logs && <details className="educationOperationSection">
      <summary>补充记录与异常事项（可选）</summary>
      <div className="educationPurposeNote"><strong>这里做什么？</strong><span>上方“6＋1教学日历”保存每一天的完整教学日报。这里只用于同一天由不同老师追加单项教学、考勤、生活管理或异常事件，一天可以多条；普通日报不需要重复填写。</span></div>
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
