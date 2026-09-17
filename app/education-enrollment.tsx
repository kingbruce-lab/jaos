"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { EducationAssessments } from "./education-assessments";
import { EducationPayments } from "./education-ledger";

type Api = <T>(path: string, options?: RequestInit, token?: string) => Promise<T>;
export type EducationOptions = { games: string[]; periods: Record<string, string>; rooms: string[]; staff_roles: string[]; fee_details: Record<string, string[]> };
type Staff = { id: string; name: string; role: string; note?: string; active?: boolean };
type Fee = { category: string; detail: string; staff_id: string | null; receivable: string; cost: string; note: string };
type StaffAssignment = { staff_id: string; name?: string; role?: string; start_date: string; end_date: string; note: string };
type Student = { id: string; student_no?: string; name: string; registration_date: string; gender: string; age: number; birth_date?: string | null; identity_masked: string; phone_masked: string; guardian_name?: string; guardian_phone_masked?: string; emergency_contact?: string; health_notes?: string; referrer_name?: string; referral_channel?: string; game: string; game_account?: string; current_rank?: string; course_period: string; study_start: string; study_end: string; accommodation_days: number; room_type: string; fee_notes: string; notes: string; learning_status?: string; receivable: string; received: string; cost: string; arrears: string; overpayment: string; version: number; fees: Fee[]; staff_assignments: StaffAssignment[] };
type Registry = { items: Student[]; has_more: boolean; summary: { count: number; receivable: string; received: string; cost: string; arrears: string } };
const money = (value: string | number) => Number(value).toLocaleString("zh-CN", { style: "currency", currency: "CNY" });
const today = () => new Date().toLocaleDateString("sv-SE");
const base = (id: string) => `v1/pm/education/cohorts/${id}`;
const blankFee = (): Fee => ({ category: "学费", detail: "课程学费", staff_id: null, receivable: "0", cost: "0", note: "" });
const courseEnd = (start: string, period: string) => {
  const parts = start.split("-").map(Number); if (parts.length !== 3 || parts.some(Number.isNaN)) return start;
  const value = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2])); value.setUTCDate(value.getUTCDate() + (period === "8_days" ? 7 : period === "3_months" ? 86 : 28));
  return value.toISOString().slice(0, 10);
};

function Classification({ options, staff, value, onChange }: { options: EducationOptions; staff: Staff[]; value: Fee; onChange: (value: Fee) => void }) {
  return <>
    <label>费用分类<select value={value.category} onChange={(e) => onChange({ ...value, category: e.target.value, detail: options.fee_details[e.target.value][0], staff_id: null, receivable: e.target.value === "学费" ? value.receivable : "0" })}>
      {Object.keys(options.fee_details).map((key) => <option key={key}>{key}</option>)}
    </select></label>
    <label>费用明细 / 人员类型<select value={value.detail} onChange={(e) => onChange({ ...value, detail: e.target.value, staff_id: null })}>
      {(options.fee_details[value.category] || []).map((key) => <option key={key}>{key}</option>)}
    </select></label>
    {value.category === "人员成本" && <label>选择人员<select value={value.staff_id || ""} required onChange={(e) => onChange({ ...value, staff_id: e.target.value })}>
      <option value="">请选择；没有人员请先在人员名册添加</option>{staff.filter((item) => item.role === value.detail && (item.active !== false || item.id === value.staff_id)).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.role}{item.active === false ? "（已移除·历史关联）" : ""}</option>)}
    </select></label>}
  </>;
}

export function EducationCostClassification({ api, token, cohortId, entry }: { api: Api; token: string; cohortId: string; entry?: { category?: string; detail?: string; staff_id?: string | null } }) {
  const [options, setOptions] = useState<EducationOptions | null>(null);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [error, setError] = useState("");
  const [fee, setFee] = useState<Fee>({ ...blankFee(), category: entry?.category || "其他", detail: entry?.detail || "其他", staff_id: entry?.staff_id || null });
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api<EducationOptions>("v1/pm/education/options", { signal: controller.signal }, token), api<{ items: Staff[] }>(`${base(cohortId)}/staff`, { signal: controller.signal }, token)])
      .then(([catalog, people]) => { if (!controller.signal.aborted) { setOptions(catalog); setStaff(people.items); } })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause.message || "费用选项加载失败"); });
    return () => controller.abort();
  }, [api, token, cohortId]);
  return <>
    {error && <p role="alert">{error}</p>}
    {options && <Classification options={options} staff={staff} value={fee} onChange={setFee} />}
    <input type="hidden" name="category" value={fee.category} /><input type="hidden" name="detail" value={fee.detail} /><input type="hidden" name="staff_id" value={fee.staff_id || ""} />
  </>;
}

function StudentForm({ student, options, staff, start, period, busy, onSubmit }: { student?: Student; options: EducationOptions; staff: Staff[]; start: string; period: string; busy: boolean; onSubmit: (event: FormEvent<HTMLFormElement>, fees: Fee[], assignments: StaffAssignment[]) => void }) {
  const [fees, setFees] = useState<Fee[]>(student?.fees || [blankFee()]);
  const [assignments, setAssignments] = useState<StaffAssignment[]>(student?.staff_assignments || []);
  const [studyStart, setStudyStart] = useState(student?.study_start || start);
  const [coursePeriod, setCoursePeriod] = useState(student?.course_period || period);
  const studyEnd = courseEnd(studyStart, coursePeriod);
  const received = student?.received || "0";
  const due = fees.reduce((sum, fee) => sum + Math.round(Number(fee.receivable || 0) * 100), 0) / 100;
  const cost = fees.reduce((sum, fee) => sum + Math.round(Number(fee.cost || 0) * 100), 0) / 100;
  const change = (index: number, fee: Fee) => setFees((current) => current.map((item, i) => i === index ? fee : item));
  return <form className="educationForm" onSubmit={(event) => onSubmit(event, fees, assignments)}>
    <label>报名日期<input name="registration_date" type="date" required defaultValue={student?.registration_date || today()} /></label>
    <label>学员姓名<input name="name" required maxLength={80} defaultValue={student?.name} /></label>
    <label>性别<select name="gender" defaultValue={student?.gender || "未填写"}><option>男</option><option>女</option><option>未填写</option></select></label>
    <label>出生日期<input name="birth_date" type="date" min="1900-01-01" max={today()} defaultValue={student?.birth_date || ""} /></label>
    <label>年龄（历史资料备用）<input name="age" type="number" min="0" max="120" step="1" defaultValue={student?.age} /><small>填写出生日期后按入营日自动计算</small></label>
    <label>身份证号<input name="identity_number" autoComplete="off" maxLength={18} placeholder={student ? `已存：${student.identity_masked || "未填写"}；留空保留` : "可暂不填写"} />{student && <span><input type="checkbox" name="clear_identity" /> 清空已存身份证号</span>}</label>
    <label>联系电话<input name="phone" type="tel" autoComplete="off" maxLength={30} placeholder={student ? `已存：${student.phone_masked || "未填写"}；留空保留` : "可填写学员或监护人电话"} />{student && <span><input type="checkbox" name="clear_phone" /> 清空已存联系电话</span>}</label>
    <label>监护人姓名<input name="guardian_name" maxLength={80} defaultValue={student?.guardian_name || ""} /></label>
    <label>监护人电话<input name="guardian_phone" type="tel" autoComplete="off" maxLength={30} placeholder={student ? `已存：${student.guardian_phone_masked || "未填写"}；留空保留` : "未成年人必填"} />{student && <span><input type="checkbox" name="clear_guardian_phone" /> 清空已存监护人电话</span>}</label>
    <label className="educationWide">紧急联系人<input name="emergency_contact" maxLength={240} defaultValue={student?.emergency_contact || ""} placeholder="姓名、关系和联系电话" /></label>
    <label className="educationWide">健康状况或过敏史<textarea name="health_notes" maxLength={2000} defaultValue={student?.health_notes || ""} placeholder="敏感信息，仅授权人员可见" /></label>
    <label>推荐人<input name="referrer_name" maxLength={120} defaultValue={student?.referrer_name || ""} placeholder="没有可留空" /></label>
    <label>推荐渠道<input name="referral_channel" maxLength={160} defaultValue={student?.referral_channel || ""} placeholder="如家长转介绍、合作机构、短视频" /></label>
    <label>游戏项目<select name="game" defaultValue={student?.game || options.games[0]}>{options.games.map((game) => <option key={game}>{game}</option>)}</select></label>
    <label>游戏账号<input name="game_account" maxLength={100} defaultValue={student?.game_account || ""} /></label>
    <label>当前段位<input name="current_rank" maxLength={100} defaultValue={student?.current_rank || ""} /></label>
    <label>课程周期<select name="course_period" value={coursePeriod} onChange={(event) => { const next = event.target.value; const end = courseEnd(studyStart, next); setCoursePeriod(next); setAssignments((items) => items.map((item) => ({ ...item, start_date: item.start_date < studyStart || item.start_date > end ? studyStart : item.start_date, end_date: item.end_date < studyStart || item.end_date > end ? end : item.end_date }))); }}>{Object.entries(options.periods).map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>
    <label>学习开始日期<input name="study_start" type="date" required value={studyStart} onChange={(event) => { const next = event.target.value; const end = courseEnd(next, coursePeriod); setStudyStart(next); setAssignments((items) => items.map((item) => ({ ...item, start_date: item.start_date < next || item.start_date > end ? next : item.start_date, end_date: item.end_date < next || item.end_date > end ? end : item.end_date }))); }} /></label>
    <label>住宿天数<input name="accommodation_days" type="number" min="0" max="366" step="1" required defaultValue={student?.accommodation_days ?? 0} /></label>
    <label>房型<select name="room_type" defaultValue={student?.room_type || "两人间"}>{options.rooms.map((room) => <option key={room}>{room}</option>)}</select></label>
    <label>学习状态<select name="learning_status" defaultValue={student?.learning_status || "已报名"}><option>已报名</option><option>待入营</option><option>在读</option><option>已结营</option><option>已退营</option></select></label>
    <div className="educationWide educationAssignments"><h4>本学员课程周期与全部师资</h4><p className="educationHint">把本学员在整个课时期间接触的教师、助教、班主任、生活老师和状态恢复师统一登记在这里。</p>
      {assignments.map((assignment, index) => <div className="educationAssignmentRow" key={`${assignment.staff_id}-${index}`}>
        <label>人员<select required value={assignment.staff_id} onChange={(event) => { const person = staff.find((item) => item.id === event.target.value); setAssignments((items) => items.map((item, i) => i === index ? { ...item, staff_id: event.target.value, name: person?.name, role: person?.role } : item)); }}><option value="">请选择人员</option>{staff.filter((item) => item.active !== false || item.id === assignment.staff_id).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.role}{item.note ? ` · ${item.note}` : ""}</option>)}</select></label>
        <label>负责开始<input type="date" required min={studyStart} max={studyEnd} value={assignment.start_date} onChange={(event) => setAssignments((items) => items.map((item, i) => i === index ? { ...item, start_date: event.target.value } : item))} /></label>
        <label>负责结束<input type="date" required min={studyStart} max={studyEnd} value={assignment.end_date} onChange={(event) => setAssignments((items) => items.map((item, i) => i === index ? { ...item, end_date: event.target.value } : item))} /></label>
        <label>分工备注<input maxLength={500} value={assignment.note} onChange={(event) => setAssignments((items) => items.map((item, i) => i === index ? { ...item, note: event.target.value } : item))} placeholder="负责课程、课时或特殊安排" /></label>
        <button type="button" disabled={busy} onClick={() => setAssignments((items) => items.filter((_, i) => i !== index))}>移除此人</button>
      </div>)}
      <button type="button" disabled={busy || assignments.length >= 100 || !staff.some((item) => item.active !== false)} onClick={() => setAssignments((items) => [...items, { staff_id: "", start_date: studyStart, end_date: studyEnd, note: "" }])}>＋ 添加本学员授课人员</button>
      {!staff.some((item) => item.active !== false) && <p className="educationHint">请先在上方人员名册连续添加教师或助教。</p>}
    </div>
    <label className="educationWide">套餐与费用备注<textarea name="fee_notes" maxLength={2000} defaultValue={student?.fee_notes} placeholder="套餐价格、优惠、特殊住宿安排等" /></label>
    <div className="educationWide"><h4>一口价套餐与实际成本</h4><p className="educationHint">学费是包含住宿和餐饮的一口价套餐，应收只在“学费”行填写；住宿、餐食、零食、活动、人员等仅记录公司实际成本，不能重复向学员计费。</p>
      {fees.map((fee, index) => <div className="educationFeeRow" key={index}>
        <Classification options={options} staff={staff} value={fee} onChange={(value) => change(index, value)} />
        <label>{fee.category === "学费" ? "套餐应收（元）" : "应收（套餐已包含）"}<input type="number" required min="0" max="9999999999.99" step="0.01" value={fee.receivable} disabled={fee.category !== "学费"} onChange={(e) => change(index, { ...fee, receivable: e.target.value })} /></label>
        <label>成本（元）<input type="number" required min="0" max="9999999999.99" step="0.01" value={fee.cost} onChange={(e) => change(index, { ...fee, cost: e.target.value })} /></label>
        <label>明细备注<input maxLength={500} value={fee.note} onChange={(e) => change(index, { ...fee, note: e.target.value })} placeholder="选择其他时可填写具体明细" /></label>
        <button type="button" disabled={busy} onClick={() => setFees((current) => current.filter((_, i) => i !== index))}>移除此费用行</button>
      </div>)}
      <button type="button" disabled={busy || fees.length >= 100} onClick={() => setFees((current) => [...current, blankFee()])}>＋ 添加费用明细</button>
    </div>
    <input name="received" type="hidden" value={received} /><p className="educationHint">累计净实收 {money(received)}。保存报名后请在“分期与收退款”逐笔登记，系统会自动更新该金额；历史导入的期初数继续保留。</p>
    <div className="educationWide educationMetrics"><article><span>应收合计费用</span><strong>{money(due)}</strong></article><article><span>成本合计</span><strong>{money(cost)}</strong></article><article><span>欠费</span><strong>{money(Math.max(0, due - Number(received)))}</strong></article>{Number(received) > due && <article><span>超收 / 预收</span><strong>{money(Number(received) - due)}</strong></article>}</div>
    <label className="educationWide">备注<textarea name="notes" maxLength={2000} defaultValue={student?.notes} /></label>
    <button className="primaryButton" disabled={busy}>{busy ? "保存中…" : student ? "保存学员修改" : "保存报名"}</button>
  </form>;
}

export function EducationEnrollment({ api, token, cohortId, start, period, canEdit, onSaved }: { api: Api; token: string; cohortId: string; start: string; period: string; canEdit: boolean; onSaved: () => void }) {
  const [options, setOptions] = useState<EducationOptions | null>(null);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [selected, setSelected] = useState<Student | null>(null);
  const [studentModule, setStudentModule] = useState<"fees" | "payments" | "assessment">("fees");
  const [identity, setIdentity] = useState<{ identity_number: string; phone: string; guardian_phone: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [staffRole, setStaffRole] = useState("");
  const [loading, setLoading] = useState(true);
  const requestId = useRef<string | null>(null);
  const staffRequestId = useRef<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api<EducationOptions>("v1/pm/education/options", { signal: controller.signal }, token), api<{ items: Staff[] }>(`${base(cohortId)}/staff`, { signal: controller.signal }, token), api<Registry>(`${base(cohortId)}/students`, { signal: controller.signal }, token)])
      .then(([catalog, people, students]) => { if (!controller.signal.aborted) { setOptions(catalog); setStaff(people.items); setRegistry(students); } })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause.message || "报名资料加载失败"); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, token, cohortId]);
  useEffect(() => { if (identity) { const timer = setTimeout(() => setIdentity(null), 60000); return () => clearTimeout(timer); } }, [identity]);

  async function refreshStudents(studentId?: string) {
    const updated = await api<Registry>(`${base(cohortId)}/students`, {}, token);
    setRegistry(updated);
    if (studentId) {
      const student = await api<Student>(`${base(cohortId)}/students/${studentId}`, {}, token);
      setSelected((current) => current?.id === studentId ? student : current);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>, fees: Fee[], staff_assignments: StaffAssignment[]) {
    event.preventDefault(); if (busy) return;
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const { clear_identity, clear_phone, clear_guardian_phone, ...fields } = values;
    const body = { ...fields, age: fields.age ? Number(fields.age) : null, birth_date: fields.birth_date || null, accommodation_days: Number(fields.accommodation_days), fees,
      staff_assignments: staff_assignments.map(({ staff_id, start_date, end_date, note }) => ({ staff_id, start_date, end_date, note })),
      identity_number: clear_identity ? "" : fields.identity_number || (selected ? null : ""),
      phone: clear_phone ? "" : fields.phone || (selected ? null : ""),
      guardian_phone: clear_guardian_phone ? "" : fields.guardian_phone || (selected ? null : ""),
      ...(selected ? { version: selected.version } : { request_id: requestId.current ||= crypto.randomUUID() }) };
    setBusy(true); setError("");
    try {
      await api(`${base(cohortId)}/students${selected ? `/${selected.id}` : ""}`, { method: selected ? "PATCH" : "POST", body: JSON.stringify(body), signal: AbortSignal.timeout(20000) }, token);
      requestId.current = null;
      void refreshStudents(selected?.id).catch((cause) => setError(cause instanceof Error ? `保存成功，但学员列表刷新失败：${cause.message}` : "保存成功，但学员列表刷新失败"));
      onSaved();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "保存失败；请刷新确认后再试"); }
    finally { setBusy(false); }
  }
  async function addStaff(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true); setError("");
    try { staffRequestId.current ||= crypto.randomUUID(); const result = await api<{ id: string }>(`${base(cohortId)}/staff`, { method: "POST", body: JSON.stringify({ ...values, request_id: staffRequestId.current }), signal: AbortSignal.timeout(20000) }, token); staffRequestId.current = null; setStaff((items) => [...items, { id: result.id, name: String(values.name), role: String(values.role), note: String(values.note || ""), active: true }]); form.reset(); setStaffRole(String(values.role)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "添加人员失败"); }
    finally { setBusy(false); }
  }
  async function view(student: Student, module: "fees" | "payments" | "assessment" = "fees") {
    if (busy) return; setBusy(true); setError(""); setIdentity(null);
    try { setSelected(await api<Student>(`${base(cohortId)}/students/${student.id}`, {}, token)); setStudentModule(module); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "加载失败"); }
    finally { setBusy(false); }
  }
  async function removeStaff(person: Staff) {
    if (busy || !canEdit || !window.confirm(`确认从本班期移除“${person.name}”？已有关联费用和评估记录会保留，后续新增记录不能再选择此人。`)) return;
    setBusy(true); setError("");
    try {
      await api(`${base(cohortId)}/staff/${person.id}`, { method: "DELETE", signal: AbortSignal.timeout(20000) }, token);
      setStaff((items) => items.map((item) => item.id === person.id ? { ...item, active: false } : item));
      onSaved();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "移除失败，请刷新核对后重试"); }
    finally { setBusy(false); }
  }
  async function reveal() {
    if (!selected || busy) return; setBusy(true); setError("");
    try { setIdentity(await api(`${base(cohortId)}/students/${selected.id}/identity`, { method: "POST" }, token)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "查看失败"); }
    finally { setBusy(false); }
  }
  async function more() {
    if (!registry || busy) return; setBusy(true);
    try { const result = await api<Registry>(`${base(cohortId)}/students?offset=${registry.items.length}`, {}, token); setRegistry({ ...result, items: [...registry.items, ...result.items] }); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "加载失败"); }
    finally { setBusy(false); }
  }
  return <section className="educationEnrollment">
    <h3>学员报名与费用管理</h3>
    <p className="educationHint">身份证和联系电话默认遮罩，仅班期负责人及管理可按需查看原文。此处资料不进入 AI 检索。</p>
    {error && <div className="educationError" role="alert">{error}</div>}{loading && <p>正在加载学员资料…</p>}
    {registry && <div className="educationMetrics"><article><span>已登记学员</span><strong>{registry.summary.count} 人</strong></article><article><span>应收合计费用</span><strong>{money(registry.summary.receivable)}</strong></article><article><span>已收金额</span><strong>{money(registry.summary.received)}</strong></article><article><span>欠费合计</span><strong>{money(registry.summary.arrears)}</strong></article><article><span>学员成本合计</span><strong>{money(registry.summary.cost)}</strong></article></div>}
    {options && <>
      <details className="educationRoster" open><summary>教师 / 助教人员名册（{staff.filter((item) => item.active !== false).length}） · 可连续添加</summary>
        <p className="educationHint">添加成功后录入区保持展开，可直接继续添加下一位。移除不删除历史费用、评估和学员师资记录，也不影响登录账号。</p>
        <div className="educationRosterGrid">{staff.filter((item) => item.active !== false).map((item) => <article key={item.id} className="educationRosterPerson">
          <span className="educationRosterAvatar" aria-hidden="true">{item.name.slice(0, 1)}</span>
          <span className="educationRosterIdentity"><strong>{item.name}</strong><small>{item.role}</small>{item.note && <em>{item.note}</em>}</span>
          {canEdit && <button type="button" disabled={busy} onClick={() => void removeStaff(item)}>移除</button>}
        </article>)}</div>
        {!staff.some((item) => item.active !== false) && <p>暂无在册人员；此名册不创建登录账号。</p>}
        {canEdit && <form className="educationForm educationStaffQuickAdd" onSubmit={(e) => void addStaff(e)}><label>人员姓名<input name="name" required maxLength={80} autoComplete="off" /></label><label>人员类型<select name="role" value={staffRole || options.staff_roles[0]} onChange={(event) => setStaffRole(event.target.value)}>{options.staff_roles.map((role) => <option key={role}>{role}</option>)}</select></label><label>人员备注{(staffRole || options.staff_roles[0]) === "其他教师" ? "（必填）" : "（选填）"}<input name="note" required={(staffRole || options.staff_roles[0]) === "其他教师"} maxLength={500} placeholder="其他教师请注明类型或职责" /></label><button className="primaryButton" disabled={busy}>{busy ? "添加中…" : "添加并继续下一位"}</button></form>}
      </details>
      {selected && <div className="educationModuleTabs"><button type="button" className={studentModule === "fees" ? "active" : ""} onClick={() => setStudentModule("fees")}>报名与套餐</button><button type="button" className={studentModule === "payments" ? "active" : ""} onClick={() => { setIdentity(null); setStudentModule("payments"); }}>分期与收退款</button>{canEdit && <button type="button" className={studentModule === "assessment" ? "active" : ""} onClick={() => { setIdentity(null); setStudentModule("assessment"); }}>教练评估体系</button>}</div>}
      {selected && studentModule === "payments" && <EducationPayments key={`${selected.id}-${selected.version}`} api={api} token={token} cohortId={cohortId} studentId={selected.id} canEdit={canEdit} onChanged={() => { void refreshStudents(selected.id).catch((cause) => setError(cause instanceof Error ? `收款已保存，但学员列表刷新失败：${cause.message}` : "收款已保存，但学员列表刷新失败")); onSaved(); }} />}
      {selected && canEdit && studentModule === "assessment" && <EducationAssessments key={selected.id} api={api} token={token} cohortId={cohortId} studentId={selected.id} studentName={selected.name} studyStart={selected.study_start} studyEnd={selected.study_end} staff={staff} />}
      {canEdit && studentModule === "fees" && <details open={!!selected} key={selected?.id || "new"}><summary>{selected ? `修改报名：${selected.name}` : "＋ 新增学员报名"}</summary>
        {selected && <><button type="button" disabled={busy} onClick={() => { setSelected(null); setIdentity(null); }}>退出修改</button><button type="button" disabled={busy} onClick={() => void reveal()}>查看证件及联系电话</button>{identity && <p className="educationIdentity">身份证号：{identity.identity_number || "未填写"}　学员电话：{identity.phone || "未填写"}　监护人电话：{identity.guardian_phone || "未填写"}<button type="button" onClick={() => setIdentity(null)}>隐藏</button></p>}</>}
        <StudentForm key={selected ? `${selected.id}-${selected.version}` : "new"} student={selected || undefined} options={options} staff={staff} start={start} period={period} busy={busy} onSubmit={(event, fees, assignments) => void save(event, fees, assignments)} />
      </details>}
      {selected && !canEdit && <div className="educationStudentRead"><h4>{selected.name} · 学习及费用总档案</h4><p>{selected.student_no || "未生成学员编号"} · {selected.gender} · {selected.age}岁 · {selected.learning_status || "已报名"}</p><p>身份证 {selected.identity_masked || "未填写"} · 电话 {selected.phone_masked || "未填写"}</p><p>{selected.study_start} 至 {selected.study_end} · {selected.game} · {options.periods[selected.course_period]} · {selected.room_type} {selected.accommodation_days}天</p><p>推荐人：{selected.referrer_name || "未填写"} · 推荐渠道：{selected.referral_channel || "未填写"}</p><h5>课时期间全部人员</h5>{selected.staff_assignments.length ? selected.staff_assignments.map((item, index) => <p key={`${item.staff_id}-${index}`}>{item.name} · {item.role} · {item.start_date} 至 {item.end_date}{item.note ? ` · ${item.note}` : ""}</p>) : <p>尚未安排人员</p>}<h5>套餐及成本</h5>{selected.fees.map((fee, index) => <p key={index}>{fee.category} / {fee.detail} · 应收 {money(fee.receivable)} · 成本 {money(fee.cost)} · {fee.note}</p>)}<p>费用备注：{selected.fee_notes}</p><p>备注：{selected.notes}</p></div>}
      <h4>学员列表</h4><div className="educationStudentList">{registry?.items.map((student) => <article key={student.id}>
        <strong>{student.name} · {student.gender} · {student.age}岁</strong><span>{student.student_no || "历史学员"} · {student.learning_status || "已报名"} · 报名：{student.registration_date}</span><span>{student.game} · {options.periods[student.course_period]}</span>
        <span>学习：{student.study_start} 至 {student.study_end} · 住宿 {student.accommodation_days}天 · {student.room_type}</span><span>推荐：{student.referrer_name || student.referral_channel ? [student.referrer_name, student.referral_channel].filter(Boolean).join(" · ") : "未填写"}</span>
        <span>师资：{student.staff_assignments?.length ? student.staff_assignments.map((item) => `${item.name}（${item.role}）`).join("、") : "尚未安排"}</span>
        <span>身份证：{student.identity_masked || "未填写"} · 电话：{student.phone_masked || "未填写"}</span>
        <span>应收 {money(student.receivable)} · 已收 {money(student.received)} · 欠费 {money(student.arrears)}{Number(student.overpayment) > 0 ? ` · 超收/预收 ${money(student.overpayment)}` : ""}</span>
        <button type="button" disabled={busy} onClick={() => void view(student)}>{canEdit ? "查看 / 修改报名费用" : "查看费用明细"}</button>
        <button type="button" disabled={busy} onClick={() => void view(student, "payments")}>分期与收退款</button>
        {canEdit && <button type="button" disabled={busy} onClick={() => void view(student, "assessment")}>教练评估</button>}
      </article>)}</div>
      {registry?.items.length === 0 && <p>暂无逐位报名记录；新增后会自动汇总人数和费用。</p>}
      {registry?.has_more && <button type="button" disabled={busy} onClick={() => void more()}>加载更多学员</button>}
    </>}
  </section>;
}
